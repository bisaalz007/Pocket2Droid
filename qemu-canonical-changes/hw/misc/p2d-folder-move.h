/* Recoverable regular-file moves for filesystems without NOREPLACE rename.
 * Included after the VCEFS path helpers; no work on guest CPU dispatch.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#define MOVE_PREFIX ".guest-move-"
#define MOVE_SUFFIX ".pending"

static int move_sync(int fd)
{
    int r;
    do { r = fsync(fd); } while (r < 0 && errno == EINTR);
    return r ? errno : 0;
}

static char *move_path(GPtrArray *parts)
{
    GString *text = g_string_new(NULL);
    for (unsigned i = 0; i < parts->len; i++) {
        if (i) { g_string_append_c(text, '/'); }
        g_string_append(text, parts->pdata[i]);
    }
    return g_string_free(text, false);
}

static char *move_digest(int fd, uint64_t size)
{
    g_autoptr(GChecksum) sum = g_checksum_new(G_CHECKSUM_SHA256);
    uint8_t bytes[65536];
    uint64_t offset = 0;
    while (offset < size) {
        ssize_t n;
        do { n = pread(fd, bytes, MIN(sizeof(bytes), size - offset), offset); }
        while (n < 0 && errno == EINTR);
        if (n <= 0) { if (!n) { errno = EIO; } return NULL; }
        g_checksum_update(sum, bytes, n);
        offset += n;
    }
    return g_strdup(g_checksum_get_string(sum));
}

static int move_write(int fd, const void *bytes, size_t size)
{
    size_t done = 0;
    while (done < size) {
        ssize_t n;
        do { n = write(fd, (const uint8_t *)bytes + done, size - done); }
        while (n < 0 && errno == EINTR);
        if (n <= 0) { return n ? errno : EIO; }
        done += n;
    }
    return 0;
}

static int move_retire(P2DImport *s, const char *record)
{
    if (unlinkat(s->move_state_fd, record, 0)) { return errno; }
    return move_sync(s->move_state_fd);
}

static int move_record(P2DImport *s, GPtrArray *from, GPtrArray *to,
                        const struct stat *st, const char *digest, char **name)
{
    g_autoptr(GKeyFile) key = g_key_file_new();
    g_autofree char *source = move_path(from), *target = move_path(to);
    g_key_file_set_string(key, "Move", "Source", source);
    g_key_file_set_string(key, "Move", "Target", target);
    g_key_file_set_string(key, "Move", "SHA256", digest);
    g_key_file_set_uint64(key, "Move", "Bytes", st->st_size);
    g_key_file_set_uint64(key, "Move", "SourceDevice", st->st_dev);
    g_key_file_set_uint64(key, "Move", "SourceInode", st->st_ino);
    g_key_file_set_boolean(key, "Move", "Claimed", false);
    size_t length;
    g_autofree char *data = g_key_file_to_data(key, &length, NULL);
    int fd = -1, error;
    for (unsigned i = 0; i < 16; i++) {
        g_free(*name);
        *name = g_strdup_printf(MOVE_PREFIX "%08x%08x" MOVE_SUFFIX,
                                g_random_int(), g_random_int());
        fd = openat(s->move_state_fd, *name,
                    O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (fd >= 0 || errno != EEXIST) { break; }
    }
    if (fd < 0) { return errno; }
    error = move_write(fd, data, length);
    if (!error) { error = move_sync(fd); }
    if (close(fd) && !error) { error = errno; }
    if (!error) { error = move_sync(s->move_state_fd); }
    return error;
}

/* The intent record predates O_EXCL creation. Claim the actual new inode
 * durably before writing any bytes; an unclaimed existing target is ambiguous. */
static int move_claim(P2DImport *s, const char *record, const struct stat *target)
{
    int fd = openat(s->move_state_fd, record,
                    O_WRONLY | O_APPEND | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) { return errno; }
    struct stat st;
    int error = 0;
    if (fstat(fd, &st)) { error = errno; }
    else if (!S_ISREG(st.st_mode) || st.st_nlink != 1 || st.st_size <= 0 ||
             st.st_size > 7168) { error = EINVAL; }
    g_autofree char *claim = g_strdup_printf("TargetDevice=%" PRIu64
                    "\nTargetInode=%" PRIu64 "\nClaimed=true\n",
                    (uint64_t)target->st_dev, (uint64_t)target->st_ino);
    if (!error) { error = move_write(fd, claim, strlen(claim)); }
    if (!error) { error = move_sync(fd); }
    if (close(fd) && !error) { error = errno; }
    return error;
}

static int move_source_matches(int dir, const char *leaf, const struct stat *old)
{
    struct stat now;
    if (fstatat(dir, leaf, &now, AT_SYMLINK_NOFOLLOW)) { return errno; }
    return S_ISREG(now.st_mode) && now.st_dev == old->st_dev &&
           now.st_ino == old->st_ino && now.st_size == old->st_size ? 0 : EBUSY;
}

static int folder_move_file(P2DImport *s, int dir, const char *leaf,
                             int dir2, const char *leaf2,
                             GPtrArray *from, GPtrArray *to)
{
    if (s->move_state_fd < 0) { return EOPNOTSUPP; }
    int in = folder_open_object(dir, leaf, O_RDONLY, true), out = -1, error;
    struct stat st, current;
    g_autofree char *digest = NULL, *record = NULL, *copied = NULL, *fresh = NULL;
    if (in < 0) { return errno; }
    if (fstat(in, &st)) { error = errno; goto done; }
    if (st.st_size < 0 || (uint64_t)st.st_size > UINT32_MAX) { error = EFBIG; goto done; }
    /* Copying cannot preserve writes to an already-open source inode. Keep
     * that case blocked rather than detach a live guest writer's save. */
    for (unsigned i = 0; i < ARRAY_SIZE(s->files); i++) {
        if (s->files[i].fd >= 0 && (s->files[i].mode & 15)) {
            if (fstat(s->files[i].fd, &current)) { error = errno; goto done; }
            if (current.st_dev == st.st_dev && current.st_ino == st.st_ino) {
                error = EBUSY; goto done;
            }
        }
    }
    digest = move_digest(in, st.st_size);
    if (!digest) { error = errno; goto done; }
    error = move_sync(in);
    if (error) { goto done; }
    error = move_record(s, from, to, &st, digest, &record);
    if (error) { s->move_blocked = true; goto done; }
    out = openat(dir2, leaf2, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW |
                 O_CLOEXEC | O_NONBLOCK, 0600);
    if (out < 0) {
        error = errno;
        int retired = move_retire(s, record);
        if (retired) { s->move_blocked = true; error = retired; }
        goto done;
    }
    struct stat published;
    if (fstat(out, &published)) { error = errno; goto incomplete; }
    error = move_claim(s, record, &published);
    if (error) { goto incomplete; }
    uint8_t bytes[65536];
    uint64_t offset = 0;
    while (offset < (uint64_t)st.st_size) {
        ssize_t n;
        do { n = pread(in, bytes, MIN(sizeof(bytes), st.st_size - offset), offset); }
        while (n < 0 && errno == EINTR);
        if (n <= 0) { error = n ? errno : EIO; goto incomplete; }
        error = move_write(out, bytes, n);
        if (error) { goto incomplete; }
        offset += n;
    }
    if (fchmod(out, st.st_mode & 0777)) { error = errno; goto incomplete; }
    struct timespec times[2] = { st.st_atim, st.st_mtim };
    if (futimens(out, times)) { error = errno; goto incomplete; }
    error = move_sync(out);
    if (error) { goto incomplete; }
    copied = move_digest(out, st.st_size); fresh = move_digest(in, st.st_size);
    if (!copied || !fresh) { error = errno; goto incomplete; }
    if (strcmp(digest, copied) || strcmp(digest, fresh)) { error = EIO; goto incomplete; }
    error = move_source_matches(dir, leaf, &st);
    if (error) { goto incomplete; }
    if (fstat(out, &published)) { error = errno; goto incomplete; }
    error = move_source_matches(dir2, leaf2, &published);
    if (error) { goto incomplete; }
    /* A close/writeback error must leave the original pathname intact. */
    if (close(out)) { out = -1; error = errno; goto incomplete; }
    out = -1;
    error = move_sync(dir2);
    if (error) { goto incomplete; }
    /* Recheck both names after potentially slow writeback/close. This detects
     * replacement during those operations; stat/unlink is not a host lock. */
    error = move_source_matches(dir2, leaf2, &published);
    if (!error) { error = move_source_matches(dir, leaf, &st); }
    if (error) { goto incomplete; }
    if (unlinkat(dir, leaf, 0)) { error = errno; goto incomplete; }
    error = move_sync(dir);
    if (error) { goto incomplete; }
    error = move_retire(s, record);
    if (error) { goto incomplete; }
    goto done;
incomplete:
    /* Never unlink a destination on failure: another host writer may have
     * replaced that pathname. Keep source/recovery data and block the card. */
    s->move_blocked = true;
    error_report("SD-card move incomplete; recovery files preserved: %s", strerror(error));
done:
    if (out >= 0) { close(out); }
    close(in);
    return error;
}

static int move_recover(P2DImport *s, const char *record)
{
    int journal = openat(s->move_state_fd, record, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    int dir = -1, dir2 = -1, in = -1, out = -1, error = EINVAL;
    struct stat st, source_st, target_st;
    g_autofree char *source = NULL, *target = NULL, *digest = NULL;
    g_autofree char *leaf = NULL, *leaf2 = NULL, *actual = NULL, *original = NULL;
    g_autofree char *checked_from = NULL, *checked_to = NULL;
    g_autoptr(GPtrArray) from = NULL, to = NULL;
    g_autoptr(GKeyFile) key = g_key_file_new();
    g_autoptr(GError) parse = NULL;
    if (journal < 0) { return errno; }
    if (fstat(journal, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        st.st_size <= 0 || st.st_size > 8192) { goto done; }
    char data[8193];
    ssize_t n = pread(journal, data, st.st_size, 0);
    if (n != st.st_size || !g_key_file_load_from_data(key, data, n, G_KEY_FILE_NONE, &parse)) { goto done; }
    source = g_key_file_get_string(key, "Move", "Source", &parse);
    if (parse) { goto done; }
    target = g_key_file_get_string(key, "Move", "Target", &parse);
    if (parse) { goto done; }
    digest = g_key_file_get_string(key, "Move", "SHA256", &parse);
    if (parse || !digest || strlen(digest) != 64) { goto done; }
    for (unsigned i = 0; i < 64; i++) { if (!g_ascii_isxdigit(digest[i])) { goto done; } }
    uint64_t size = g_key_file_get_uint64(key, "Move", "Bytes", &parse);
    if (parse || size > UINT32_MAX) { goto done; }
    uint64_t device = g_key_file_get_uint64(key, "Move", "SourceDevice", &parse);
    if (parse) { goto done; }
    uint64_t inode = g_key_file_get_uint64(key, "Move", "SourceInode", &parse);
    if (parse) { goto done; }
    bool claimed = g_key_file_get_boolean(key, "Move", "Claimed", &parse);
    if (parse) { goto done; }
    uint64_t target_device = 0, target_inode = 0;
    if (claimed) {
        target_device = g_key_file_get_uint64(key, "Move", "TargetDevice", &parse);
        if (parse) { goto done; }
        target_inode = g_key_file_get_uint64(key, "Move", "TargetInode", &parse);
        if (parse) { goto done; }
    }
    from = folder_parts(source, false); to = folder_parts(target, false);
    if (!from || !to || !from->len || !to->len) { goto done; }
    checked_from = move_path(from); checked_to = move_path(to);
    if (strcmp(source, checked_from) || strcmp(target, checked_to) || !strcmp(source, target)) { goto done; }
    error = folder_parent(s, from, from->len, true, &dir, &leaf);
    if (error) { goto done; }
    error = folder_parent(s, to, to->len, true, &dir2, &leaf2);
    if (error) { goto done; }
    in = folder_open_object(dir, leaf, O_RDONLY, true);
    if (in < 0 && errno != ENOENT) { error = errno; goto done; }
    if (in >= 0) {
        if (fstat(in, &source_st)) { error = errno; goto done; }
        if (source_st.st_dev != device || source_st.st_ino != inode || source_st.st_size != size) { error = EBUSY; goto done; }
        original = move_digest(in, size);
        if (!original || strcmp(original, digest)) { error = EIO; goto done; }
    }
    out = folder_open_object(dir2, leaf2, O_RDONLY, true);
    if (out < 0) {
        error = errno;
        /* No target was ever published: unchanged source makes rollback safe. */
        if (error == ENOENT && in >= 0) { error = move_retire(s, record); }
        goto done;
    }
    if (!claimed) { error = EBUSY; goto done; }
    if (fstat(out, &target_st)) { error = errno; goto done; }
    if (target_st.st_dev != target_device || target_st.st_ino != target_inode ||
        (device == target_device && inode == target_inode)) { error = EBUSY; goto done; }
    if (target_st.st_size != size) { error = EIO; goto done; }
    actual = move_digest(out, size);
    if (!actual || strcmp(actual, digest)) { error = EIO; goto done; }
    /* Payload completion can precede metadata publication. While the original
     * still exists, restore its attributes/times before the deletion boundary.
     * An absent original has already passed normal metadata+fsync publication. */
    if (in >= 0) {
        if (fchmod(out, source_st.st_mode & 0777)) { error = errno; goto done; }
        struct timespec times[2] = { source_st.st_atim, source_st.st_mtim };
        if (futimens(out, times)) { error = errno; goto done; }
    }
    error = move_sync(out);
    if (!error) {
        if (close(out)) { error = errno; }
        out = -1;
    }
    if (!error) { error = move_sync(dir2); }
    if (error) { goto done; }
    error = move_source_matches(dir2, leaf2, &target_st);
    if (error) { goto done; }
    if (in >= 0) {
        error = move_source_matches(dir, leaf, &source_st);
        if (error) { goto done; }
        if (unlinkat(dir, leaf, 0)) { error = errno; goto done; }
    }
    /* Source removal may have succeeded before an earlier directory-sync
     * failure. Make that deletion durable even when the name is now absent. */
    error = move_sync(dir);
    if (error) { goto done; }
    error = move_retire(s, record);
done:
    if (in >= 0) { close(in); } if (out >= 0) { close(out); }
    if (dir >= 0) { close(dir); } if (dir2 >= 0) { close(dir2); }
    close(journal);
    return error;
}

static bool folder_move_state_load(P2DImport *s, const char *state,
                                   const char *shared, Error **errp)
{
    if (!state) { return true; }
    g_autofree char *private = realpath(state, NULL), *root = realpath(shared, NULL);
    if (!private || !root || (!strncmp(private, root, strlen(root)) &&
        (private[strlen(root)] == '/' || !private[strlen(root)]))) {
        error_setg(errp, "SD-card move recovery requires an existing private directory outside the shared root");
        return false;
    }
    s->move_state_fd = open(state, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (s->move_state_fd < 0) { error_setg_errno(errp, errno, "Cannot open SD-card move recovery directory"); return false; }
    s->move_lock_fd = openat(s->move_state_fd, ".guest-move.lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat st;
    if (s->move_lock_fd < 0 || fstat(s->move_lock_fd, &st) || !S_ISREG(st.st_mode) ||
        st.st_nlink != 1 || flock(s->move_lock_fd, LOCK_EX | LOCK_NB)) {
        error_setg(errp, "SD-card move recovery guard unavailable or owned by another engine"); return false;
    }
    int scan = folder_directory(s->move_state_fd), error = 0;
    DIR *directory = scan >= 0 ? fdopendir(scan) : NULL;
    if (!directory) {
        if (scan >= 0) { close(scan); }
        error_setg_errno(errp, errno, "Cannot scan SD-card move recovery records"); return false;
    }
    for (;;) {
        errno = 0;
        struct dirent *entry = readdir(directory);
        if (!entry) { error = errno; break; }
        if (g_str_has_prefix(entry->d_name, MOVE_PREFIX) && g_str_has_suffix(entry->d_name, MOVE_SUFFIX)) {
            error = move_recover(s, entry->d_name);
            if (error) { break; }
        }
    }
    closedir(directory);
    if (error) {
        s->move_blocked = true;
        error_setg_errno(errp, error, "SD-card move recovery incomplete; source/destination preserved"); return false;
    }
    return true;
}
