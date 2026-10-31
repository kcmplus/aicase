"""Build a release from tracked application sources and the compiled admin UI."""
import hashlib
import io
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def allowed_source(name):
    if name in {'deploy/dev/aicase-dev-ai-cleanup.service', 'deploy/dev/aicase-dev-ai-cleanup.timer'}:
        return True
    path = Path(name)
    if not (name.startswith('backend/') or name.startswith('frontend/storefront/')):
        return False
    if any(part.startswith('.') or part in {'__pycache__', 'node_modules', 'media', 'staticfiles'}
           for part in path.parts):
        return False
    return path.suffix not in {'.pyc', '.sqlite3', '.pem', '.key', '.log'} and 'db.sqlite3' not in name


def build(output=None):
    output = Path(output or ROOT / 'dist-release')
    admin = ROOT / 'frontend/admin/dist'
    if not (admin / 'index.html').is_file():
        raise SystemExit('Build the admin first: npm run build:admin')
    output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with tarfile.open(output / 'release.tar.gz', 'w:gz') as archive:
        for name in sorted(filter(allowed_source, tracked)):
            source = ROOT / name
            if not source.is_file() or source.is_symlink():
                raise SystemExit(f'Expected a regular source file: {name}')
            archive.add(source, arcname=name, recursive=False)
        for source in sorted(admin.rglob('*')):
            if source.is_symlink():
                raise SystemExit('Admin build must not contain symlinks')
            if source.is_file():
                archive.add(source, arcname='frontend/storefront/admin/' + source.relative_to(admin).as_posix())
        data = (commit + '\n').encode()
        entry = tarfile.TarInfo('VERSION')
        entry.size, entry.mode = len(data), 0o644
        archive.addfile(entry, io.BytesIO(data))
    shutil.copyfile(ROOT / 'deploy/dev/deploy.sh', output / 'deploy.sh')
    checksums = []
    for name in ['release.tar.gz', 'deploy.sh']:
        digest = hashlib.sha256((output / name).read_bytes()).hexdigest()
        checksums.append(f'{digest}  {name}\n')
    (output / 'SHA256SUMS').write_text(''.join(checksums))
    print(f'Release {commit}: {output}')


if __name__ == '__main__':
    build()
