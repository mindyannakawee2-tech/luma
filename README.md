# LUMA V1.2.0

```bash
luma install lumacenter.github.io/hello main
```

LUMA converts it to:

```text
https://lumacenter.github.io/hello
```

Then checks:

```text
https://lumacenter.github.io/hello/releases/main/package.luma
https://lumacenter.github.io/hello/main/package.luma
https://lumacenter.github.io/hello/package.luma
https://raw.githubusercontent.com/lumacenter/hello/main/releases/main/package.luma
https://raw.githubusercontent.com/lumacenter/hello/main/package.luma
https://raw.githubusercontent.com/lumacenter/hello/main/main/package.luma
```

## Install

```bash
curl -fsSL https://mindyannakawee2-tech.github.io/luma/install.sh | bash
```

## Uninstall LUMA manager

```bash
curl -fsSL https://mindyannakawee2-tech.github.io/luma/uninstall.sh | bash

```

Or:

```bash
sudo luma self-uninstall --yes
```

Purge all LUMA data too:

```bash
sudo luma self-uninstall --yes --purge
```

## Create and pack a package

```bash
mkdir -p ~/Desktop/luma-test
cd ~/Desktop/luma-test

luma template hello --lang python
cd hello
luma check .
luma pack
```

Install local package:

```bash
luma install package.luma
luma run hello
```

## Publish to GitHub Pages

Put the file here in your GitHub repo:

```text
releases/main/package.luma
```

Then install:

```bash
luma install lumacenter.github.io/hello main
```

## Repo website install

```bash
luma pkg-get mindyannakawee2-tech.github.io/luma-site
luma search notes
luma install aurora-notes
```

## Commands

```text
luma version
luma doctor
luma template <folder> [--id id] [--lang python|shell|java|c|cpp]
luma init <folder> [--id id] [--lang python|shell|java|c|cpp]
luma pack [folder] [-o package.luma]
luma check <package-or-folder>
luma install <package-id-or-url-or-file> [release]
luma pkg-get <repo-url>
luma repos
luma repo-remove <name-or-url>
luma search <text>
luma info <package-id>
luma list
luma run <package-id>
luma remove <package-id>
luma self-uninstall --yes [--purge]
```
