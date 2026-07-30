#!/usr/bin/env python3
"""
LUMA Package Manager V1.3.0

Changes in 1.2.0:
  - Better URL auto-fix: lumacenter.github.io/pkg becomes https://lumacenter.github.io/pkg
  - Added installer uninstall.sh
  - Added luma self-uninstall helper command
  - Improved direct install handling for .github.io package roots
  - Keeps V1 commands: template, init, pack, check, install, pkg-get, repos, search, info, list, run, remove

Package format:
  package.luma = zip file containing:
    MANIFEST/config.txt
    SCRIPTS/run.sh
    SCRIPTS/error_handler.sh        optional
    SCRIPTS/crash_handler.sh        optional
    ASSETS/...                      optional
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

VERSION = "1.3.0"

LUMA_HOME = Path(os.environ.get("LUMA_HOME", Path.home() / ".local" / "share" / "luma"))
APPS_DIR = LUMA_HOME / "apps"
CACHE_DIR = LUMA_HOME / "cache"
REPOS_FILE = LUMA_HOME / "repos.json"
BIN_DIR = Path.home() / ".local" / "bin"


def ensure_dirs() -> None:
    LUMA_HOME.mkdir(parents=True, exist_ok=True)
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    if not REPOS_FILE.exists():
        save_repos([])


def die(message: str, code: int = 1) -> None:
    print(f"LUMA error: {message}", file=sys.stderr)
    raise SystemExit(code)


def say(message: str) -> None:
    print(f"LUMA: {message}")


def slugify(value: str) -> str:
    value = str(value).strip().lower().replace(" ", "-")
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in value).strip("-") or "package"


def make_executable(path: Path) -> None:
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def looks_like_url(value: str) -> bool:
    value = value.strip()
    if value.startswith(("http://", "https://")):
        return True
    if ".github.io" in value:
        return True
    if "." in value and "/" in value and not Path(value).exists():
        return True
    return False


def normalize_url(value: str) -> str:
    """
    Auto-add https:// to repo/package sources before installation.
    Examples:
      lumacenter.github.io/hello        -> https://lumacenter.github.io/hello
      github.com/user/repo              -> https://github.com/user/repo
      https://already.example/file.luma  -> unchanged
    """
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_config_text(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def config_to_text(data: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in data.items()) + "\n"


def load_repos() -> list[dict[str, Any]]:
    ensure_dirs()
    try:
        raw = json.loads(REPOS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("repos", [])
    except Exception:
        pass
    return []


def save_repos(repos: list[dict[str, Any]]) -> None:
    LUMA_HOME.mkdir(parents=True, exist_ok=True)
    REPOS_FILE.write_text(json.dumps(repos, indent=2), encoding="utf-8")


def http_get_bytes(url: str, timeout: int = 120) -> bytes:
    url = normalize_url(url) if looks_like_url(url) else url
    req = urllib.request.Request(url, headers={"User-Agent": f"LUMA/{VERSION}", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def download_file(url: str, dest: Path) -> None:
    url = normalize_url(url) if looks_like_url(url) else url
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": f"LUMA/{VERSION}", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response, dest.open("wb") as f:
            shutil.copyfileobj(response, f)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e.reason}") from e


def url_exists(url: str) -> bool:
    url = normalize_url(url) if looks_like_url(url) else url
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": f"LUMA/{VERSION}"})
        with urllib.request.urlopen(req, timeout=20):
            return True
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"LUMA/{VERSION}", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=20):
            return True
    except Exception:
        return False


def fetch_json(url: str) -> dict[str, Any]:
    return json.loads(http_get_bytes(url).decode("utf-8"))


def read_manifest_from_folder(folder: Path) -> dict[str, str]:
    candidates = [
        folder / "MANIFEST" / "config.txt",
        folder / "manifest" / "config.txt",
        folder / "config.txt",
        folder / "MANIFEST" / "manifest.json",
        folder / "manifest.json",
    ]
    for path in candidates:
        if path.exists():
            raw = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix == ".json":
                obj = json.loads(raw)
                return {str(k): str(v) for k, v in obj.items()}
            return parse_config_text(raw)
    die(f"No manifest found in folder: {folder}")


def read_manifest_from_luma(package_file: Path) -> dict[str, str]:
    if not zipfile.is_zipfile(package_file):
        die(f"Not a valid .luma zip file: {package_file}")
    with zipfile.ZipFile(package_file, "r") as z:
        names = z.namelist()
        found = None
        for candidate in ["MANIFEST/config.txt", "manifest/config.txt", "config.txt", "MANIFEST/manifest.json", "manifest.json"]:
            if candidate in names:
                found = candidate
                break
        if found is None:
            die("Package missing MANIFEST/config.txt")
        raw = z.read(found).decode("utf-8", errors="replace")
    if found.endswith(".json"):
        obj = json.loads(raw)
        return {str(k): str(v) for k, v in obj.items()}
    return parse_config_text(raw)


def read_manifest(path: Path) -> dict[str, str]:
    if path.is_dir():
        return read_manifest_from_folder(path)
    return read_manifest_from_luma(path)


def parse_dependencies_text(text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        if ":" in line:
            dep_type, value = line.split(":", 1)
            dep_type = dep_type.strip().lower()
            value = value.strip()
        else:
            dep_type = "command"
            value = line.strip()
        if value:
            deps.append({"type": dep_type, "value": value, "line": str(line_no)})
    return deps


def read_dependencies_from_folder(folder: Path) -> list[dict[str, str]]:
    for path in [
        folder / "MANIFEST" / "dependencies.txt",
        folder / "MANIFEST" / "depedencies.txt",
        folder / "dependencies.txt",
        folder / "depedencies.txt",
    ]:
        if path.exists():
            return parse_dependencies_text(path.read_text(encoding="utf-8", errors="replace"))
    return []


def read_dependencies_from_luma(package_file: Path) -> list[dict[str, str]]:
    if not zipfile.is_zipfile(package_file):
        die(f"Not a valid .luma zip file: {package_file}")
    with zipfile.ZipFile(package_file, "r") as z:
        names = z.namelist()
        for candidate in [
            "MANIFEST/dependencies.txt",
            "MANIFEST/depedencies.txt",
            "dependencies.txt",
            "depedencies.txt",
        ]:
            if candidate in names:
                return parse_dependencies_text(z.read(candidate).decode("utf-8", errors="replace"))
    return []


def read_dependencies(path: Path) -> list[dict[str, str]]:
    return read_dependencies_from_folder(path) if path.is_dir() else read_dependencies_from_luma(path)


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def luma_package_installed(package_id: str) -> bool:
    return (APPS_DIR / slugify(package_id) / ".luma-installed.json").exists()


def apt_package_installed(package: str) -> bool:
    if not command_exists("dpkg-query"):
        return False
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Status}", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0 and "install ok installed" in result.stdout


def pip_package_installed(package: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", package],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def flatpak_installed(app_id: str) -> bool:
    if not command_exists("flatpak"):
        return False
    result = subprocess.run(["flatpak", "info", app_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def dependency_status(dep: dict[str, str]) -> tuple[bool, str]:
    dep_type = dep["type"]
    value = dep["value"]
    if dep_type == "command":
        return command_exists(value), f"command {value}"
    if dep_type == "apt":
        return apt_package_installed(value), f"apt package {value}"
    if dep_type == "pip":
        return pip_package_installed(value), f"pip package {value}"
    if dep_type == "flatpak":
        return flatpak_installed(value), f"flatpak app {value}"
    if dep_type == "luma":
        return luma_package_installed(value), f"LUMA package {value}"
    return False, f"unknown dependency type {dep_type}:{value}"


def install_dependency(dep: dict[str, str], yes: bool = False) -> None:
    dep_type = dep["type"]
    value = dep["value"]
    ok, label = dependency_status(dep)
    if ok:
        say(f"Dependency already installed: {label}")
        return
    say(f"Installing dependency: {label}")
    if not yes:
        answer = input(f"Install {label}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            die(f"Dependency installation cancelled: {label}")
    if dep_type == "command":
        die(f"Missing command: {value}. Use apt:{value}, pip:{value}, flatpak:{value}, or install it manually.")
    if dep_type == "apt":
        if not command_exists("apt"):
            die("apt not found on this system")
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", value], check=True)
        return
    if dep_type == "pip":
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", value], check=True)
        return
    if dep_type == "flatpak":
        if not command_exists("flatpak"):
            die("flatpak not found. Install flatpak first.")
        subprocess.run(["flatpak", "install", "-y", "flathub", value], check=True)
        return
    if dep_type == "luma":
        fake_args = argparse.Namespace(package=value, release=None, install_deps=yes, yes=yes)
        cmd_install(fake_args)
        return
    die(f"Unknown dependency type: {dep_type}")


def check_dependencies_for_path(path: Path, install_missing: bool = False, yes: bool = False) -> None:
    deps = read_dependencies(path)
    if not deps:
        say("No dependencies found.")
        return
    say("Checking dependencies:")
    missing = []
    for dep in deps:
        ok, label = dependency_status(dep)
        if ok:
            print(f"  [OK]      {label}")
        else:
            print(f"  [MISSING] {label}")
            missing.append(dep)
    if missing and not install_missing:
        die(f"Missing dependencies. Install them with: luma install-deps {path}")
    if install_missing:
        for dep in missing:
            install_dependency(dep, yes=yes)


def validate_manifest(manifest: dict[str, str]) -> list[str]:
    errors = []
    if not manifest.get("id") and not manifest.get("name"):
        errors.append("MANIFEST/config.txt needs id= or name=")
    if not manifest.get("version"):
        errors.append("MANIFEST/config.txt needs version=")
    entry = manifest.get("entry") or manifest.get("run") or "SCRIPTS/run.sh"
    if not entry:
        errors.append("MANIFEST/config.txt needs entry=SCRIPTS/run.sh")
    return errors


def package_id_from_manifest(manifest: dict[str, str]) -> str:
    return slugify(manifest.get("id") or manifest.get("name") or "package")


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                die(f"Unsafe path in package: {member.filename}")
        z.extractall(dest)


def is_direct_source(value: str) -> bool:
    if Path(value).exists():
        return False
    return looks_like_url(value)


def github_pages_raw_candidates(source: str, release: str | None) -> list[str]:
    parsed = urllib.parse.urlparse(normalize_url(source))
    host = parsed.netloc
    parts = [p for p in parsed.path.split("/") if p]
    if not host.endswith(".github.io") or not parts:
        return []
    owner = host.removesuffix(".github.io")
    repo = parts[0]
    rel = release or "stable"
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/releases/{rel}/package.luma",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/package.luma",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/{rel}/package.luma",
    ]


def github_repo_raw_candidates(source: str, release: str | None) -> list[str]:
    parsed = urllib.parse.urlparse(normalize_url(source))
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.netloc != "github.com" or len(parts) < 2:
        return []
    owner, repo = parts[0], parts[1].removesuffix(".git")
    rel = release or "stable"
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/releases/{rel}/package.luma",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/package.luma",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/{rel}/package.luma",
    ]


def build_direct_candidates(source: str, release: str | None) -> list[str]:
    source = normalize_url(source).rstrip("/")
    candidates = []
    if source.endswith(".luma"):
        candidates.append(source)
    elif release:
        candidates.append(f"{source}/releases/{release}/package.luma")
        candidates.append(f"{source}/{release}/package.luma")
        candidates.append(f"{source}/package.luma")
    else:
        candidates.append(f"{source}/package.luma")
        candidates.append(f"{source}/releases/stable/package.luma")
    candidates.extend(github_pages_raw_candidates(source, release))
    candidates.extend(github_repo_raw_candidates(source, release))
    result, seen = [], set()
    for url in candidates:
        if url not in seen:
            result.append(url)
            seen.add(url)
    return result


def resolve_direct_package_url(source: str, release: str | None) -> str:
    candidates = build_direct_candidates(source, release)
    say("Direct install mode")
    say("Checking package URLs:")
    for url in candidates:
        print(f"  - {url}")
    for url in candidates:
        if url_exists(url):
            say(f"Found package: {url}")
            return url
    die("Package file not found.\nCreate one of these files:\n" + "\n".join(f"  {url}" for url in candidates))


def create_template(folder: Path, package_id: str | None = None, language: str = "python") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "MANIFEST").mkdir(exist_ok=True)
    (folder / "SCRIPTS").mkdir(exist_ok=True)
    (folder / "ASSETS").mkdir(exist_ok=True)

    pkg_id = slugify(package_id or folder.name)
    name = pkg_id.replace("-", " ").title()
    config = {
        "id": pkg_id,
        "name": name,
        "version": "1.0.0",
        "author": "Unknown",
        "entry": "SCRIPTS/run.sh",
        "description": "A LUMA package.",
    }
    (folder / "MANIFEST" / "config.txt").write_text(config_to_text(config), encoding="utf-8")

    (folder / "MANIFEST" / "dependencies.txt").write_text(
        "# LUMA dependencies file\n"
        "# Supported formats:\n"
        "#   command:python3\n"
        "#   apt:python3\n"
        "#   pip:requests\n"
        "#   flatpak:org.videolan.VLC\n"
        "#   luma:other-package\n"
        "\n"
        "command:python3\n",
        encoding="utf-8",
    )

    language = language.lower().strip()
    if language in ("python", "py"):
        (folder / "ASSETS" / "main.py").write_text('print("Hello from LUMA package!")\n', encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
python3 ASSETS/main.py "$@"
"""
    elif language in ("shell", "bash", "sh"):
        (folder / "ASSETS" / "main.sh").write_text('#!/usr/bin/env bash\necho "Hello from LUMA shell package!"\n', encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
bash ASSETS/main.sh "$@"
"""
    elif language == "java":
        (folder / "ASSETS" / "Main.java").write_text("""public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from LUMA Java package!");
    }
}
""", encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
javac ASSETS/Main.java
java -cp ASSETS Main "$@"
"""
    elif language == "c":
        (folder / "ASSETS" / "main.c").write_text("""#include <stdio.h>
int main(void) {
    puts("Hello from LUMA C package!");
    return 0;
}
""", encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
cc ASSETS/main.c -o ASSETS/main
ASSETS/main "$@"
"""
    elif language in ("cpp", "c++"):
        (folder / "ASSETS" / "main.cpp").write_text("""#include <iostream>
int main() {
    std::cout << "Hello from LUMA C++ package!" << std::endl;
    return 0;
}
""", encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
c++ ASSETS/main.cpp -o ASSETS/main
ASSETS/main "$@"
"""
    else:
        (folder / "ASSETS" / "main.txt").write_text("Hello from LUMA package!\n", encoding="utf-8")
        run = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
cat ASSETS/main.txt
"""
    if language == "java":
        (folder / "MANIFEST" / "dependencies.txt").write_text("apt:default-jdk\n", encoding="utf-8")
    elif language == "c" or language in ("cpp", "c++"):
        (folder / "MANIFEST" / "dependencies.txt").write_text("apt:build-essential\n", encoding="utf-8")

    (folder / "SCRIPTS" / "run.sh").write_text(run, encoding="utf-8")
    (folder / "SCRIPTS" / "error_handler.sh").write_text("#!/usr/bin/env bash\necho \"LUMA package error: $1\" >&2\n", encoding="utf-8")
    (folder / "SCRIPTS" / "crash_handler.sh").write_text("#!/usr/bin/env bash\necho \"LUMA package crashed: $1\" >&2\n", encoding="utf-8")
    for p in [folder / "SCRIPTS" / "run.sh", folder / "SCRIPTS" / "error_handler.sh", folder / "SCRIPTS" / "crash_handler.sh"]:
        make_executable(p)
    say(f"Created template: {folder}")


def pack_folder(folder: Path, output: Path) -> None:
    folder = folder.resolve()
    if not (folder / "MANIFEST" / "config.txt").exists():
        die(f"Missing {folder / 'MANIFEST' / 'config.txt'}")
    if not (folder / "SCRIPTS" / "run.sh").exists():
        die(f"Missing {folder / 'SCRIPTS' / 'run.sh'}")
    manifest = read_manifest_from_folder(folder)
    errors = validate_manifest(manifest)
    if errors:
        die("\n".join(errors))
    make_executable(folder / "SCRIPTS" / "run.sh")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for top in ["MANIFEST", "SCRIPTS", "ASSETS"]:
            root = folder / top
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file():
                        z.write(path, path.relative_to(folder))
    say(f"Packed: {output}")
    say(f"SHA256: {sha256_file(output)}")


def install_luma_file(package_file: Path, source_url: str | None = None, install_deps: bool = False, yes: bool = False) -> None:
    manifest = read_manifest_from_luma(package_file)
    errors = validate_manifest(manifest)
    if errors:
        die("\n".join(errors))
    if read_dependencies_from_luma(package_file):
        check_dependencies_for_path(package_file, install_missing=install_deps, yes=yes)
    pkg_id = package_id_from_manifest(manifest)
    name = manifest.get("name") or pkg_id
    version = manifest.get("version", "0.0.0")
    entry = manifest.get("entry") or manifest.get("run") or "SCRIPTS/run.sh"
    install_dir = APPS_DIR / pkg_id
    if install_dir.exists():
        shutil.rmtree(install_dir)
    say(f"Installing {name} {version}")
    safe_extract_zip(package_file, install_dir)
    entry_path = install_dir / entry
    if not entry_path.exists():
        die(f"Entry script does not exist after install: {entry}")
    make_executable(entry_path)
    meta = {"id": pkg_id, "name": name, "version": version, "entry": entry, "source_url": source_url, "sha256": sha256_file(package_file), "dependencies": read_dependencies_from_luma(package_file)}
    (install_dir / ".luma-installed.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    launcher = BIN_DIR / pkg_id
    launcher.write_text(f"""#!/usr/bin/env bash
cd "{install_dir}"
exec "{entry_path}" "$@"
""", encoding="utf-8")
    make_executable(launcher)
    say(f"Installed: {pkg_id}")
    say(f"Run with: luma run {pkg_id}")
    say(f"Shell shortcut: {launcher}")


def resolve_relative_url(base_url: str, maybe_relative: str) -> str:
    return urllib.parse.urljoin(base_url, maybe_relative)


def find_package_in_repos(package_id: str) -> dict[str, Any] | None:
    for repo in load_repos():
        url = repo.get("url")
        if not url:
            continue
        try:
            data = fetch_json(url)
        except Exception:
            continue
        for pkg in data.get("packages", []):
            if pkg.get("id") == package_id or pkg.get("name") == package_id:
                pkg["_repo_url"] = url
                return pkg
    return None


def cmd_version(args): print(f"LUMA {VERSION}")


def cmd_doctor(args):
    ensure_dirs()
    print(f"LUMA version: {VERSION}")
    print(f"LUMA_HOME:    {LUMA_HOME}")
    print(f"APPS_DIR:     {APPS_DIR}")
    print(f"CACHE_DIR:    {CACHE_DIR}")
    print(f"REPOS_FILE:   {REPOS_FILE}")
    print(f"BIN_DIR:      {BIN_DIR}")
    print(f"Python:       {sys.version.split()[0]}")
    print("zip support:  yes")
    if str(BIN_DIR) in os.environ.get("PATH", ""):
        print("PATH:         ~/.local/bin is available")
    else:
        print("PATH:         ~/.local/bin is NOT in PATH")
        print('Tip:          echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')


def cmd_template(args): create_template(Path(args.folder), args.id, args.lang)
def cmd_init(args): create_template(Path(args.folder), args.id, args.lang)


def cmd_pack(args):
    folder = Path(args.folder or ".")
    output = Path(args.output or "package.luma")
    if not output.is_absolute():
        output = folder / output
    pack_folder(folder, output)


def cmd_check(args):
    target = Path(args.target)
    manifest = read_manifest(target)
    errors = validate_manifest(manifest)
    print("Manifest:")
    for k, v in manifest.items():
        print(f"  {k}: {v}")
    deps = read_dependencies(target)
    print("\nDependencies:")
    if deps:
        for dep in deps:
            ok, label = dependency_status(dep)
            mark = "OK" if ok else "MISSING"
            print(f"  [{mark}] {dep['type']}:{dep['value']}  ({label})")
    else:
        print("  none")
    if errors:
        print("\nProblems:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    if target.is_file():
        print(f"\nSHA256: {sha256_file(target)}")
    print("\nOK: package looks valid")


def cmd_deps(args):
    check_dependencies_for_path(Path(args.target), install_missing=False, yes=args.yes)


def cmd_install_deps(args):
    check_dependencies_for_path(Path(args.target), install_missing=True, yes=args.yes)


def cmd_install(args):
    ensure_dirs()
    source = args.package.strip()
    release = args.release
    cache_file = CACHE_DIR / "downloaded.package.luma"

    if Path(source).exists() and Path(source).is_file():
        install_luma_file(Path(source), source_url=str(Path(source).resolve()), install_deps=args.install_deps, yes=args.yes)
        return

    if is_direct_source(source):
        source = normalize_url(source)
        package_url = resolve_direct_package_url(source, release)
        say(f"Downloading package: {package_url}")
        try:
            download_file(package_url, cache_file)
        except RuntimeError as e:
            die(str(e))
        install_luma_file(cache_file, source_url=package_url, install_deps=args.install_deps, yes=args.yes)
        return

    pkg = find_package_in_repos(source)
    if not pkg:
        die(f"Package not found in added repos: {source}. Add a repo with: luma pkg-get <repo-url>")
    file_url = pkg.get("file") or pkg.get("url") or pkg.get("download")
    if not file_url:
        die(f"Package {source} has no file/url/download field")
    package_url = resolve_relative_url(pkg.get("_repo_url", ""), file_url)
    package_url = normalize_url(package_url) if looks_like_url(package_url) else package_url
    say(f"Downloading package: {package_url}")
    try:
        download_file(package_url, cache_file)
    except RuntimeError as e:
        die(str(e))
    expected_sha = pkg.get("sha256")
    if expected_sha and not str(expected_sha).startswith("replace-"):
        actual = sha256_file(cache_file)
        if actual.lower() != str(expected_sha).lower():
            die(f"SHA256 mismatch. Expected {expected_sha}, got {actual}")
    install_luma_file(cache_file, source_url=package_url, install_deps=args.install_deps, yes=args.yes)


def cmd_pkg_get(args):
    url = normalize_url(args.repo_url)
    if url.endswith(".json"):
        candidates = [url]
    else:
        base = url.rstrip("/")
        candidates = [f"{base}/packages/index.json", f"{base}/index.json"]
    chosen = data = None
    for c in candidates:
        try:
            data = fetch_json(c)
            chosen = c
            break
        except Exception:
            continue
    if not chosen or not data:
        die("Could not find repo index. Tried:\n" + "\n".join(f"  {c}" for c in candidates))
    repo_name = data.get("repo", {}).get("name") or data.get("name") or chosen
    repos = [r for r in load_repos() if r.get("url") != chosen and r.get("name") != repo_name]
    repos.append({"name": repo_name, "url": chosen})
    save_repos(repos)
    say(f"Added repo: {repo_name}")
    say(chosen)


def cmd_repos(args):
    repos = load_repos()
    if not repos:
        print("No repos added.")
        print("Add one with: luma pkg-get <repo-url>")
        return
    for i, repo in enumerate(repos, 1):
        print(f"{i}. {repo.get('name', 'unknown')}")
        print(f"   {repo.get('url')}")


def cmd_repo_remove(args):
    key = args.name_or_url
    repos = load_repos()
    new = [r for r in repos if r.get("name") != key and r.get("url") != key]
    if len(new) == len(repos):
        die(f"Repo not found: {key}")
    save_repos(new)
    say(f"Removed repo: {key}")


def cmd_search(args):
    query = args.text.lower()
    found = 0
    for repo in load_repos():
        url = repo.get("url")
        if not url:
            continue
        try:
            data = fetch_json(url)
        except Exception:
            continue
        for pkg in data.get("packages", []):
            blob = " ".join(str(pkg.get(k, "")) for k in ["id", "name", "description", "language"])
            blob += " " + " ".join(pkg.get("tags", []))
            if query in blob.lower():
                found += 1
                print(f"{pkg.get('id')} - {pkg.get('name')} {pkg.get('version', '')}")
                print(f"  {pkg.get('description', '')}")
                print(f"  repo: {repo.get('name')}")
    if not found:
        print("No packages found.")


def cmd_info(args):
    app_dir = APPS_DIR / args.package
    meta_file = app_dir / ".luma-installed.json"
    if meta_file.exists():
        print(json.dumps(json.loads(meta_file.read_text(encoding="utf-8")), indent=2))
        return
    pkg = find_package_in_repos(args.package)
    if pkg:
        print(json.dumps({k: v for k, v in pkg.items() if not k.startswith("_")}, indent=2))
        return
    die(f"No installed package or repo package found: {args.package}")


def cmd_list(args):
    ensure_dirs()
    apps = sorted(p for p in APPS_DIR.iterdir() if p.is_dir())
    if not apps:
        print("No packages installed.")
        return
    for app in apps:
        meta_file = app / ".luma-installed.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            print(f"{meta.get('id')} {meta.get('version')} - {meta.get('name')}")
        else:
            print(app.name)


def cmd_run(args):
    app_dir = APPS_DIR / args.package
    meta_file = app_dir / ".luma-installed.json"
    if not meta_file.exists():
        die(f"Package not installed: {args.package}")
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    entry = app_dir / meta.get("entry", "SCRIPTS/run.sh")
    if not entry.exists():
        die(f"Entry script missing: {entry}")
    make_executable(entry)
    subprocess.run([str(entry), *args.extra], cwd=str(app_dir), check=False)


def cmd_remove(args):
    app_dir = APPS_DIR / args.package
    if not app_dir.exists():
        die(f"Package not installed: {args.package}")
    shutil.rmtree(app_dir)
    launcher = BIN_DIR / args.package
    if launcher.exists():
        launcher.unlink()
    say(f"Removed: {args.package}")


def cmd_self_uninstall(args):
    print("This removes the LUMA manager files, but keeps installed apps unless --purge is used.")
    if not args.yes:
        die("Run again with: luma self-uninstall --yes")
    for path in [Path("/usr/local/bin/luma"), Path("/opt/luma/manager/luma.py")]:
        try:
            if path.exists():
                path.unlink()
                print(f"Removed {path}")
        except PermissionError:
            die("Permission denied. Use: sudo luma self-uninstall --yes")
    try:
        manager = Path("/opt/luma/manager")
        if manager.exists() and not any(manager.iterdir()):
            manager.rmdir()
        opt = Path("/opt/luma")
        if opt.exists() and not any(opt.iterdir()):
            opt.rmdir()
    except Exception:
        pass
    if args.purge and LUMA_HOME.exists():
        shutil.rmtree(LUMA_HOME)
        print(f"Purged {LUMA_HOME}")
    print("LUMA uninstalled.")


def build_parser():
    parser = argparse.ArgumentParser(prog="luma", description="LUMA Package Manager V1.3")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", help="show LUMA version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("doctor", help="check LUMA setup")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("template", help="create a package template")
    p.add_argument("folder")
    p.add_argument("--id")
    p.add_argument("--lang", default="python", help="python, shell, java, c, cpp")
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("init", help="same as template")
    p.add_argument("folder")
    p.add_argument("--id")
    p.add_argument("--lang", default="python", help="python, shell, java, c, cpp")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("pack", help="pack a folder into package.luma")
    p.add_argument("folder", nargs="?", default=".")
    p.add_argument("-o", "--output", default="package.luma")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("check", help="check a package folder or .luma file")
    p.add_argument("target")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("deps", help="check dependencies from MANIFEST/dependencies.txt")
    p.add_argument("target")
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_deps)

    p = sub.add_parser("install-deps", help="install dependencies from MANIFEST/dependencies.txt")
    p.add_argument("target")
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_install_deps)

    p = sub.add_parser("install", help="install package by id, file, URL, or GitHub Pages root")
    p.add_argument("package")
    p.add_argument("release", nargs="?")
    p.add_argument("--install-deps", action="store_true", help="install missing dependencies before installing")
    p.add_argument("-y", "--yes", action="store_true", help="yes to dependency install prompts")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("pkg-get", help="add a repo index")
    p.add_argument("repo_url")
    p.set_defaults(func=cmd_pkg_get)

    p = sub.add_parser("repos", help="list added repos")
    p.set_defaults(func=cmd_repos)

    p = sub.add_parser("repo-remove", help="remove a repo")
    p.add_argument("name_or_url")
    p.set_defaults(func=cmd_repo_remove)

    p = sub.add_parser("search", help="search packages in added repos")
    p.add_argument("text")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("info", help="show installed package or repo package info")
    p.add_argument("package")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("list", help="list installed packages")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("run", help="run an installed package")
    p.add_argument("package")
    p.add_argument("extra", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("remove", help="remove installed package")
    p.add_argument("package")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("self-uninstall", help="remove LUMA manager files")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--purge", action="store_true", help="also delete ~/.local/share/luma")
    p.set_defaults(func=cmd_self_uninstall)

    return parser


def main() -> int:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
