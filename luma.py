#!/usr/bin/env python3
"""
LUMA Package Manager v0.3
Custom package manager for Auralis-style .luma packages.

Supported now:
- create-template
- pack <folder>
- install <package.luma / URL / app-id>
- online repos via pkg-get
- list
- info <app_id>
- run <app_id>
- remove <app_id>
- doctor

Package format:
package.luma is a ZIP file containing:
MANIFEST/config.txt
MANIFEST/icon.png optional
SCRIPTS/run.sh optional
SCRIPTS/run.ps1 optional
ASSETS/...
"""

import argparse
import configparser
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import json
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path

LUMA_VERSION = "0.3.0"

IS_WINDOWS = platform.system().lower() == "windows"
IS_MACOS = platform.system().lower() == "darwin"
IS_LINUX = platform.system().lower() == "linux"


def default_root() -> Path:
    env_root = os.environ.get("LUMA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "LUMA"

    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / "LUMA"

    return Path.home() / ".local" / "share" / "luma"


ROOT = default_root()
APPS_DIR = ROOT / "apps"
REGISTRY_DIR = ROOT / "registry"
CACHE_DIR = ROOT / "cache"
REPOS_DIR = ROOT / "repos"
REPO_INDEX_DIR = REPOS_DIR / "indexes"
REPO_FILE = REPOS_DIR / "repos.json"


class LumaError(Exception):
    pass


def ensure_dirs() -> None:
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPO_INDEX_DIR.mkdir(parents=True, exist_ok=True)


def read_manifest_from_folder(folder: Path) -> dict:
    cfg_path = folder / "MANIFEST" / "config.txt"
    if not cfg_path.exists():
        raise LumaError("Missing MANIFEST/config.txt")

    parser = configparser.ConfigParser()
    text = cfg_path.read_text(encoding="utf-8")

    # Allow simple KEY=VALUE files without [app] header.
    if not text.strip().startswith("["):
        text = "[app]\n" + text

    parser.read_string(text)
    data = dict(parser["app"])

    required = ["app_id", "app_name", "version", "type"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise LumaError("Missing required manifest keys: " + ", ".join(missing))

    return data


def app_install_path(app_id: str) -> Path:
    safe_id = app_id.replace("/", "_").replace("\\", "_")
    return APPS_DIR / safe_id


def registry_path(app_id: str) -> Path:
    safe_id = app_id.replace("/", "_").replace("\\", "_")
    return REGISTRY_DIR / f"{safe_id}.txt"


def write_registry(manifest: dict, install_path: Path) -> None:
    app_id = manifest["app_id"]
    lines = []
    for k in sorted(manifest.keys()):
        lines.append(f"{k}={manifest[k]}")
    lines.append(f"install_path={install_path}")
    registry_path(app_id).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_registry(app_id: str) -> dict:
    path = registry_path(app_id)
    if not path.exists():
        raise LumaError(f"App not installed: {app_id}")
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def make_executable(path: Path) -> None:
    if path.exists() and not IS_WINDOWS:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def cmd_create_template(args: argparse.Namespace) -> None:
    folder = Path(args.folder).expanduser().resolve()
    if folder.exists() and any(folder.iterdir()):
        raise LumaError(f"Folder exists and is not empty: {folder}")

    (folder / "MANIFEST").mkdir(parents=True, exist_ok=True)
    (folder / "SCRIPTS").mkdir(parents=True, exist_ok=True)
    (folder / "ASSETS" / "src").mkdir(parents=True, exist_ok=True)
    (folder / "ASSETS" / "assets").mkdir(parents=True, exist_ok=True)
    (folder / "ASSETS" / "bin" / "linux").mkdir(parents=True, exist_ok=True)
    (folder / "ASSETS" / "bin" / "windows").mkdir(parents=True, exist_ok=True)
    (folder / "ASSETS" / "bin" / "macos").mkdir(parents=True, exist_ok=True)

    (folder / "MANIFEST" / "config.txt").write_text("""APP_ID=org.auralis.hello
APP_NAME=LUMA Hello
VERSION=1.0.0
AUTHOR=Auralis
TYPE=python
MAIN=ASSETS/src/main.py
ICON=MANIFEST/icon.png
LINUX_RUN=SCRIPTS/run.sh
MACOS_RUN=SCRIPTS/run.sh
WINDOWS_RUN=SCRIPTS/run.ps1
CATEGORY=Utility
DESCRIPTION=Example LUMA package.
""", encoding="utf-8")

    (folder / "ASSETS" / "src" / "main.py").write_text("""#!/usr/bin/env python3
print("Hello from a .luma package!")
print("This app is running through the custom LUMA package manager.")
""", encoding="utf-8")

    (folder / "SCRIPTS" / "run.sh").write_text("""#!/usr/bin/env bash
set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$APP_DIR/ASSETS/src/main.py"
""", encoding="utf-8")

    (folder / "SCRIPTS" / "run.ps1").write_text("""$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
python "$AppDir\\ASSETS\\src\\main.py"
""", encoding="utf-8")

    (folder / "SCRIPTS" / "error_handler.sh").write_text("""#!/usr/bin/env bash
echo "LUMA app error: $1" >&2
exit 1
""", encoding="utf-8")

    (folder / "SCRIPTS" / "crash_handler.sh").write_text("""#!/usr/bin/env bash
echo "LUMA app crashed: $1" >&2
exit 1
""", encoding="utf-8")

    # Tiny placeholder, not real png. Apps can replace it.
    (folder / "MANIFEST" / "icon.png").write_bytes(b"LUMA ICON PLACEHOLDER\n")

    make_executable(folder / "SCRIPTS" / "run.sh")
    make_executable(folder / "SCRIPTS" / "error_handler.sh")
    make_executable(folder / "SCRIPTS" / "crash_handler.sh")

    print(f"Created template: {folder}")
    print(f"Pack it with: luma pack {folder}")


def cmd_pack(args: argparse.Namespace) -> None:
    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists():
        raise LumaError(f"Folder not found: {folder}")

    manifest = read_manifest_from_folder(folder)
    out = Path(args.output).expanduser().resolve() if args.output else folder.parent / f"{manifest['app_id']}_{manifest['version']}.luma"

    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in folder.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(folder).as_posix())

    print(f"Packed: {out}")



def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def url_join(base: str, path: str) -> str:
    return urllib.parse.urljoin(base.rstrip("/") + "/", path)


def repo_name_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    raw = (parsed.netloc + parsed.path).strip("/").replace("/", "_").replace(".", "_")
    if not raw:
        raw = "repo"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return f"{raw}_{digest}"


def load_repos() -> list:
    ensure_dirs()
    if not REPO_FILE.exists():
        return []
    try:
        data = json.loads(REPO_FILE.read_text(encoding="utf-8"))
        return data.get("repos", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        return []


def save_repos(repos: list) -> None:
    ensure_dirs()
    REPO_FILE.write_text(json.dumps({"repos": repos}, indent=2) + "\n", encoding="utf-8")


def download_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)


def normalize_repo_url(repo_url: str) -> tuple[str, str]:
    """Return (base_url, index_url). Accepts either repo base URL or direct packages.json URL."""
    if repo_url.endswith(".json"):
        index_url = repo_url
        base_url = repo_url.rsplit("/", 1)[0]
    else:
        base_url = repo_url.rstrip("/")
        index_url = base_url + "/packages.json"
    return base_url, index_url


def fetch_repo_index(repo_url: str) -> dict:
    base_url, index_url = normalize_repo_url(repo_url)
    text = download_text(index_url)
    try:
        index = json.loads(text)
    except json.JSONDecodeError as e:
        raise LumaError(f"Repo index is not valid JSON: {index_url}: {e}")
    if "packages" not in index or not isinstance(index["packages"], list):
        raise LumaError("Repo index must contain a packages list")
    index["_base_url"] = index.get("base_url") or base_url
    index["_index_url"] = index_url
    return index


def add_or_refresh_repo(repo_url: str, name: str | None = None) -> dict:
    ensure_dirs()
    base_url, index_url = normalize_repo_url(repo_url)
    index = fetch_repo_index(repo_url)
    repo_name = name or index.get("name") or repo_name_from_url(base_url)

    repos = load_repos()
    repos = [r for r in repos if r.get("name") != repo_name and r.get("url") != base_url]
    repos.append({"name": repo_name, "url": base_url, "index_url": index_url})
    save_repos(repos)

    index_path = REPO_INDEX_DIR / f"{repo_name}.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return {"name": repo_name, "url": base_url, "index": index}


def iter_repo_indexes() -> list:
    repos = load_repos()
    result = []
    for repo in repos:
        path = REPO_INDEX_DIR / f"{repo.get('name')}.json"
        if not path.exists():
            continue
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
            result.append((repo, index))
        except json.JSONDecodeError:
            continue
    return result


def find_package_in_repos(app_id: str):
    for repo, index in iter_repo_indexes():
        for pkg in index.get("packages", []):
            ids = [pkg.get("app_id"), pkg.get("id"), pkg.get("name")]
            if app_id in ids:
                return repo, index, pkg
    return None


def package_download_url(repo: dict, index: dict, pkg: dict) -> str:
    url = pkg.get("url") or pkg.get("file") or pkg.get("path")
    if not url:
        raise LumaError("Package entry has no url/file/path")
    if is_url(url):
        return url
    base_url = index.get("_base_url") or repo.get("url")
    return url_join(base_url, url)


def verify_sha256(path: Path, expected: str | None) -> None:
    if not expected:
        return
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected.lower():
        raise LumaError(f"SHA256 mismatch. Expected {expected}, got {actual}")


def install_package_file(pkg_path: Path, force: bool = False) -> dict:
    ensure_dirs()
    if not pkg_path.exists():
        raise LumaError(f"Package not found: {pkg_path}")

    with tempfile.TemporaryDirectory(prefix="luma-install-") as td:
        tmp = Path(td)
        try:
            with zipfile.ZipFile(pkg_path, "r") as zf:
                zf.extractall(tmp)
        except zipfile.BadZipFile:
            raise LumaError("Invalid .luma package. A .luma package must be a ZIP archive.")

        manifest = read_manifest_from_folder(tmp)
        app_id = manifest["app_id"]
        dest = app_install_path(app_id)

        if dest.exists():
            if not force:
                raise LumaError(f"App already installed: {app_id}. Use --force to reinstall.")
            shutil.rmtree(dest)

        shutil.copytree(tmp, dest)
        for script in ["run.sh", "error_handler.sh", "crash_handler.sh"]:
            make_executable(dest / "SCRIPTS" / script)

        write_registry(manifest, dest)
        return manifest


def install_from_repo(app_id: str, force: bool = False) -> dict:
    found = find_package_in_repos(app_id)
    if not found:
        raise LumaError(f"Package not found in added repos: {app_id}. Add a repo with: luma pkg-get <repo-url>")
    repo, index, pkg = found
    url = package_download_url(repo, index, pkg)
    filename = Path(urllib.parse.urlparse(url).path).name or f"{app_id}.luma"
    dest = CACHE_DIR / filename
    print(f"Downloading {app_id} from {repo.get('name')}...")
    print(url)
    download_file(url, dest)
    verify_sha256(dest, pkg.get("sha256"))
    manifest = install_package_file(dest, force=force)
    return manifest


def cmd_pkg_get(args: argparse.Namespace) -> None:
    added = add_or_refresh_repo(args.repo_url, args.name)
    packages = added["index"].get("packages", [])
    print(f"Added/refreshed repo: {added['name']}")
    print(f"URL: {added['url']}")
    if packages:
        print("Packages:")
        for pkg in packages:
            print(f"  {pkg.get('app_id') or pkg.get('id')}  {pkg.get('version', '')}  {pkg.get('name', '')}")
    else:
        print("No packages found in repo.")



def manifest_from_luma_file(pkg_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="luma-read-") as td:
        tmp = Path(td)
        try:
            with zipfile.ZipFile(pkg_path, "r") as zf:
                zf.extractall(tmp)
        except zipfile.BadZipFile:
            raise LumaError(f"Invalid .luma package: {pkg_path}")
        return read_manifest_from_folder(tmp)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_make_repo(args: argparse.Namespace) -> None:
    repo = Path(args.folder).expanduser().resolve()
    packages_dir = repo / "packages"
    icons_dir = repo / "icons"
    packages_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    package_entries = []
    for pkg_file in sorted(packages_dir.glob("*.luma")):
        manifest = manifest_from_luma_file(pkg_file)
        icon_rel = ""
        icon_path = manifest.get("icon")
        if icon_path:
            with tempfile.TemporaryDirectory(prefix="luma-icon-") as td:
                tmp = Path(td)
                with zipfile.ZipFile(pkg_file, "r") as zf:
                    try:
                        zf.extract(icon_path, tmp)
                        src_icon = tmp / icon_path
                        icon_name = f"{manifest['app_id']}.png"
                        shutil.copyfile(src_icon, icons_dir / icon_name)
                        icon_rel = f"icons/{icon_name}"
                    except KeyError:
                        icon_rel = ""

        entry = {
            "app_id": manifest.get("app_id"),
            "name": manifest.get("app_name"),
            "version": manifest.get("version"),
            "description": manifest.get("description", ""),
            "category": manifest.get("category", ""),
            "file": f"packages/{pkg_file.name}",
            "sha256": sha256_file(pkg_file),
        }
        if icon_rel:
            entry["icon"] = icon_rel
        package_entries.append(entry)

    index = {
        "repo_format": "luma-repo-v1",
        "name": args.name or repo.name,
        "description": args.description or "LUMA package repository.",
        "packages": package_entries,
    }
    (repo / "packages.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote repo index: {repo / 'packages.json'}")
    print(f"Packages: {len(package_entries)}")
    print("Upload this folder to GitHub Pages or any static web host.")


def cmd_repo_list(args: argparse.Namespace) -> None:
    repos = load_repos()
    if not repos:
        print("No LUMA repos added.")
        return
    for repo in repos:
        print(f"{repo.get('name')}  {repo.get('url')}")


def cmd_repo_refresh(args: argparse.Namespace) -> None:
    repos = load_repos()
    if not repos:
        print("No LUMA repos added.")
        return
    for repo in repos:
        added = add_or_refresh_repo(repo["url"], repo.get("name"))
        count = len(added["index"].get("packages", []))
        print(f"Refreshed {added['name']}: {count} packages")


def cmd_search(args: argparse.Namespace) -> None:
    query = args.query.lower()
    found = False
    for repo, index in iter_repo_indexes():
        for pkg in index.get("packages", []):
            hay = " ".join(str(pkg.get(k, "")) for k in ["app_id", "id", "name", "description", "category"]).lower()
            if query in hay:
                found = True
                print(f"{pkg.get('app_id') or pkg.get('id')}  {pkg.get('version', '')}  {pkg.get('name', '')}  [{repo.get('name')}]")
    if not found:
        print("No packages found.")


def cmd_install(args: argparse.Namespace) -> None:
    ensure_dirs()

    # Special user-friendly form:
    #   luma install pkg-get https://username.github.io/repo
    #   luma install pkg-get https://username.github.io/repo org.auralis.app
    if args.package == "pkg-get":
        if not args.extra:
            raise LumaError("Usage: luma install pkg-get <repo-url> [app-id]")
        repo_url = args.extra[0]
        added = add_or_refresh_repo(repo_url, None)
        print(f"Added/refreshed repo: {added['name']}")
        if len(args.extra) >= 2:
            manifest = install_from_repo(args.extra[1], force=args.force)
            print(f"Installed: {manifest['app_name']} ({manifest['app_id']})")
            print(f"Run it with: luma run {manifest['app_id']}")
        else:
            print("Packages:")
            for pkg in added["index"].get("packages", []):
                print(f"  {pkg.get('app_id') or pkg.get('id')}  {pkg.get('version', '')}  {pkg.get('name', '')}")
            print("Install one with: luma install <app-id>")
        return

    # Direct URL to a .luma file.
    if is_url(args.package):
        filename = Path(urllib.parse.urlparse(args.package).path).name or "downloaded.luma"
        pkg_path = CACHE_DIR / filename
        print(f"Downloading package: {args.package}")
        download_file(args.package, pkg_path)
        manifest = install_package_file(pkg_path, force=args.force)
        print(f"Installed: {manifest['app_name']} ({manifest['app_id']})")
        print(f"Run it with: luma run {manifest['app_id']}")
        return

    # Local file install.
    local_pkg = Path(args.package).expanduser()
    if local_pkg.exists():
        manifest = install_package_file(local_pkg.resolve(), force=args.force)
        print(f"Installed: {manifest['app_name']} ({manifest['app_id']})")
        print(f"Run it with: luma run {manifest['app_id']}")
        return

    # App ID install from added repos.
    manifest = install_from_repo(args.package, force=args.force)
    print(f"Installed: {manifest['app_name']} ({manifest['app_id']})")
    print(f"Run it with: luma run {manifest['app_id']}")


def installed_apps() -> list:
    ensure_dirs()
    apps = []
    for reg in sorted(REGISTRY_DIR.glob("*.txt")):
        data = {}
        for line in reg.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
        if data:
            apps.append(data)
    return apps


def cmd_list(args: argparse.Namespace) -> None:
    apps = installed_apps()
    if not apps:
        print("No LUMA apps installed.")
        return
    for app in apps:
        print(f"{app.get('app_id')}  {app.get('version')}  {app.get('app_name')}")


def cmd_info(args: argparse.Namespace) -> None:
    data = read_registry(args.app_id)
    for k in sorted(data.keys()):
        print(f"{k}={data[k]}")


def choose_run_command(manifest: dict, install_path: Path) -> list:
    app_type = manifest.get("type", "").lower()

    if IS_WINDOWS:
        run_script = manifest.get("windows_run", "SCRIPTS/run.ps1")
        ps1 = install_path / run_script
        if ps1.exists():
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)]
    else:
        run_key = "macos_run" if IS_MACOS else "linux_run"
        run_script = manifest.get(run_key, "SCRIPTS/run.sh")
        sh = install_path / run_script
        if sh.exists():
            make_executable(sh)
            return [str(sh)]

    main = manifest.get("main")
    if main:
        main_path = install_path / main
        if app_type == "python":
            return ["python3" if not IS_WINDOWS else "python", str(main_path)]
        if app_type == "node":
            return ["node", str(main_path)]
        if app_type in ["java", "jar"]:
            jar = manifest.get("jar") or manifest.get("main")
            if jar:
                return ["java", "-jar", str(install_path / jar)]
        if app_type == "native":
            key = "windows_binary" if IS_WINDOWS else "macos_binary" if IS_MACOS else "linux_binary"
            binary = manifest.get(key)
            if binary:
                bin_path = install_path / binary
                make_executable(bin_path)
                return [str(bin_path)]

    raise LumaError("No runnable script or supported MAIN found.")


def cmd_run(args: argparse.Namespace) -> None:
    data = read_registry(args.app_id)
    install_path = Path(data["install_path"])
    manifest = read_manifest_from_folder(install_path)
    cmd = choose_run_command(manifest, install_path)
    subprocess.run(cmd, check=True)


def cmd_remove(args: argparse.Namespace) -> None:
    data = read_registry(args.app_id)
    install_path = Path(data["install_path"])
    if install_path.exists():
        shutil.rmtree(install_path)
    reg = registry_path(args.app_id)
    if reg.exists():
        reg.unlink()
    print(f"Removed: {args.app_id}")



def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def detect_linux_package_manager() -> str:
    for name in ["apt", "dnf", "zypper", "pacman", "apk", "xbps-install", "eopkg"]:
        if command_exists(name):
            return name
    return "unknown"


def cmd_doctor(args: argparse.Namespace) -> None:
    print(f"LUMA version: {LUMA_VERSION}")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Data root: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    if IS_LINUX:
        print(f"Detected package manager: {detect_linux_package_manager()}")
    checks = [
        ("python3", "Python apps"),
        ("java", "JAR/Java apps"),
        ("node", "Node.js apps"),
        ("gcc", "C source build support"),
        ("g++", "C++ source build support"),
    ]
    for cmd, label in checks:
        print(f"{cmd}: {'OK' if command_exists(cmd) else 'missing'}  ({label})")

def cmd_root(args: argparse.Namespace) -> None:
    ensure_dirs()
    print(ROOT)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="luma", description="LUMA custom package manager")
    p.add_argument("--version", action="version", version=f"LUMA {LUMA_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("create-template", help="Create a template LUMA package folder")
    s.add_argument("folder", nargs="?", default="hello-luma-package")
    s.set_defaults(func=cmd_create_template)

    s = sub.add_parser("pack", help="Pack a folder into .luma")
    s.add_argument("folder")
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_pack)

    s = sub.add_parser("install", help="Install local .luma, URL, app ID, or pkg-get repo")
    s.add_argument("package")
    s.add_argument("extra", nargs="*")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("pkg-get", help="Add/refresh an online LUMA repo")
    s.add_argument("repo_url")
    s.add_argument("--name")
    s.set_defaults(func=cmd_pkg_get)

    s = sub.add_parser("search", help="Search packages in added repos")
    s.add_argument("query")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("make-repo", help="Generate packages.json for a repo folder")
    s.add_argument("folder")
    s.add_argument("--name")
    s.add_argument("--description")
    s.set_defaults(func=cmd_make_repo)

    repo = sub.add_parser("repo", help="Manage LUMA repos")
    repo_sub = repo.add_subparsers(dest="repo_cmd", required=True)
    r = repo_sub.add_parser("list", help="List added repos")
    r.set_defaults(func=cmd_repo_list)
    r = repo_sub.add_parser("refresh", help="Refresh all added repos")
    r.set_defaults(func=cmd_repo_refresh)

    s = sub.add_parser("list", help="List installed apps")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("info", help="Show app info")
    s.add_argument("app_id")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("run", help="Run installed app")
    s.add_argument("app_id")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("remove", help="Remove installed app")
    s.add_argument("app_id")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("root", help="Show LUMA data root")
    s.set_defaults(func=cmd_root)

    s = sub.add_parser("doctor", help="Check LUMA and common runtimes")
    s.set_defaults(func=cmd_doctor)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"LUMA run failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode
    except LumaError as e:
        print(f"LUMA error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
