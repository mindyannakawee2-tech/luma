# LUMA GitHub Upload Folder

This folder is ready to upload to your GitHub Pages repo, for example:

```text
https://github.com/mindyannakawee2-tech/luma-site
```

After GitHub Pages is enabled, users can install LUMA with:

```bash
curl -fsSL https://mindyannakawee2-tech.github.io/luma-site/install.sh | bash
```

For a different GitHub Pages URL:

```bash
curl -fsSL https://YOUR.github.io/luma-site/install.sh | LUMA_BASE_URL=https://YOUR.github.io/luma-site bash
```

## Upload layout

```text
luma-site
├── index.html
├── install.sh
├── uninstall.sh
├── luma.py
├── packages.json
├── packages
│   └── org.auralis.hello_1.0.0.luma
├── icons
│   └── org.auralis.hello.png
├── releases
│   └── luma_pkg_manager_v0.3.zip
└── .nojekyll
```

## Add this site as a LUMA app repo

```bash
luma install pkg-get https://mindyannakawee2-tech.github.io/luma-site
luma search hello
luma install org.auralis.hello
luma run org.auralis.hello
```

## Custom repo URL

If you upload to another GitHub Pages URL, replace the URL:

```bash
luma install pkg-get https://YOUR.github.io/YOUR-REPO
```
