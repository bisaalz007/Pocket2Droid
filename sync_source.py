"""Materialise the reviewed QEMU source in a space-free native Linux cache."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent / "qemu"
CACHE = Path("/opt/pocket2droid-tcg-build/source")
BASE = "f9587d4045c67cd0d8d8bdcd5d0bb5b6b395b63c"


def git_names(*arguments: str, root=None) -> list[str]:
    checkout = Path(root or SOURCE)
    windows_git = Path('/mnt/c/Program Files/Git/cmd/git.exe')
    # WSL metadata queries over a large NTFS checkout are very slow. Native
    # Windows Git reads the same repository; Linux Git still owns Linux caches.
    parts = checkout.parts
    if len(parts) > 3 and parts[1] == 'mnt' and len(parts[2]) == 1 and windows_git.is_file():
        windows_path = parts[2].upper() + ':\\' + '\\'.join(parts[3:])
        command = [str(windows_git), '-c', 'core.autocrlf=false', '-C', windows_path]
    else:
        command = ['git', '-C', str(checkout)]
    data = subprocess.check_output([*command, *arguments])
    return [name.decode() for name in data.split(b"\0") if name]


def main() -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.resolve() != CACHE:
        raise ValueError("Native source cache must not redirect through a symlink")
    if not (CACHE / ".git").is_dir():
        subprocess.run(["git", "clone", "--local", "--no-hardlinks", str(SOURCE), str(CACHE)], check=True)
    native_base = subprocess.check_output(["git", "-C", str(CACHE), "rev-parse", "HEAD"], text=True).strip()
    if native_base != BASE:
        raise ValueError("Native cache base does not match the reviewed QEMU revision")
    if git_names("diff", "--name-only", "-z", "--diff-filter=D", BASE):
        raise ValueError("Source deletions require deliberate cache handling; no automatic deletion")
    names = set(git_names("diff", "--name-only", "-z", "--diff-filter=ACMR", BASE))
    names.update(git_names("ls-files", "--others", "--exclude-standard", "-z"))
    record = CACHE.parent / (CACHE.name + '.sync.json')
    previous = json.loads(record.read_text()) if record.exists() else {}
    if previous and previous.get('base') != BASE:
        raise ValueError('Cache synchronization record has a different base')
    owned = set(previous.get('paths', {}))
    cache_tracked = set(git_names('diff', '--name-only', '-z', BASE, root=CACHE))
    cache_added = set(git_names('ls-files', '--others', '--exclude-standard', '-z', root=CACHE))
    unexpected = cache_added - names - owned
    if unexpected:
        raise ValueError(f'unowned cache source paths: {sorted(unexpected)}')
    checked = names | owned | cache_tracked
    hashes = {}
    for name in sorted(checked):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
            raise ValueError('Source name escapes its isolated checkout/cache')
        original = SOURCE / name
        target = CACHE / name
        if not original.resolve().is_relative_to(SOURCE) or not target.resolve().is_relative_to(CACHE):
            raise ValueError("Changed source path escapes its isolated checkout/cache")
        if not original.exists():
            if name not in owned or name not in cache_added:
                raise ValueError('Only a recorded local addition may be removed from cache')
            target.unlink(missing_ok=True)
            continue
        if not target.exists() or original.read_bytes() != target.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        if source_hash != hashlib.sha256(target.read_bytes()).hexdigest():
            raise ValueError('Cache readback differs from authoritative source')
        if name in names:
            hashes[name] = source_hash
    temporary = record.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'base': BASE, 'paths': hashes}, indent=2) + '\n')
    temporary.replace(record)
    print(f"Source cache synchronised: {len(checked)} paths reconciled and verified", flush=True)


if __name__ == "__main__":
    main()
