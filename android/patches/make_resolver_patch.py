"""Regenerate the small private-resolver patch against the pinned release."""
from pathlib import Path
import difflib
source=Path('/opt/pocket2droid-network-integration/deps/libslirp-v4.9.5/src/slirp.c').read_text()
helper=r'''
#include <fcntl.h>
/* Pocket2Droid: each engine owns a bounded, atomically replaced private file.
 * DNS calls are infrequent; read at each new query instead of caching stale
 * network addresses. Linux without an explicit override retains upstream DNS.
 */
static const char *p2d_resolver_path(void)
{
    const char *path = getenv("P2D_SLIRP_RESOLV_CONF");
#ifdef __ANDROID__
    return path && path[0] == '/' ? path : "";
#else
    return path;
#endif
}
static int p2d_private_dns(const char *path, int af, void *address,
                           uint16_t *port, uint32_t *scope)
{
    struct stat st;
    char data[4097], token[257];
    int fd, result = -1;
    ssize_t size;
    if (!path || path[0] != '/') { return -1; }
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) { return -1; }
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size > 4096) {
        close(fd); return -1;
    }
    size = read(fd, data, sizeof(data));
    close(fd);
    if (size < 0 || size > 4096) { return -1; }
    data[size] = 0;
    char *save, *line = strtok_r(data, "\n", &save);
    while (line) {
        if (sscanf(line, "nameserver%*[ \t]%256s", token) == 1) {
            char *zone = strchr(token, '%');
            uint32_t index = 0;
            if (zone) {
                *zone++ = 0;
                char *end;
                unsigned long n = strtoul(zone, &end, 10);
                index = *zone && !*end && n <= UINT32_MAX ? n : if_nametoindex(zone);
                if (!index) { line = strtok_r(NULL, "\n", &save); continue; }
            }
            if (inet_pton(af, token, address) == 1) {
                *port = htons(53);
                if (scope) { *scope = index; }
                result = 0; break;
            }
        }
        line = strtok_r(NULL, "\n", &save);
    }
    return result;
}
'''
marker='static int get_dns_addr_cached(void *pdns_addr, void *cached_addr,'
start=source.index('#else // !defined(_WIN32) && !defined(__APPLE__)')
pos=source.index(marker,start)
new=source[:pos]+helper+'\n'+source[pos:]
for declaration,args in [('    static struct stat dns_addr_stat;', 'AF_INET, pdns_addr, pdns_port, NULL'),('    static struct stat dns6_addr_stat;', 'AF_INET6, pdns6_addr, pdns6_port, scope_id')]:
    new=new.replace(declaration,declaration+'\n    const char *private_path = p2d_resolver_path();\n    if (private_path) { return p2d_private_dns(private_path, '+args+'); }',1)
patch=''.join(difflib.unified_diff(source.splitlines(True),new.splitlines(True),fromfile='a/src/slirp.c',tofile='b/src/slirp.c'))
Path(__file__).with_name('libslirp-android-resolver.patch').write_text(patch)
