#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import yaml

DOTNET_GENERATOR_URL = "https://github.com/flatpak/flatpak-builder-tools/raw/fdbe66a48b7450f3c18ab2cb8ff31be704846600/dotnet/flatpak-dotnet-generator.py"
ARCHITECTURES = [
    ("aarch64", "linux-arm64"),
    ("x86_64", "linux-x64"),
]
MANIFEST_PATH = "net.openra.OpenRA.yaml"
NUGET_SOURCES_PATH = "nuget-sources.json"
DOTNET_PROJECTS = ["OpenRA.sln"]
MODULE_NAME = "OpenRA"


def download(url, path):
    print(f"Download {url!r}", file=sys.stderr)
    with urllib.request.urlopen(url) as src:
        with open(path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def main():
    print(f"Working directory {os.getcwd()!r}")
    with open(MANIFEST_PATH, "rb") as f:
        manifest = yaml.load(f, yaml.Loader)
    runtime_version = manifest["runtime-version"]
    dotnet_version = next(
        filter(
            None,
            (
                re.match(r"^org.freedesktop.Sdk.Extension.dotnet(\d+)$|", s).group(1)
                for s in manifest["sdk-extensions"]
            ),
        )
    )
    module = next(filter(lambda m: m["name"] == MODULE_NAME, manifest["modules"]))
    source_archive_url = module["sources"][0]["url"]
    with tempfile.TemporaryDirectory(dir=os.path.curdir) as tmpDir:
        print(f"Temporary directory {tmpDir!r}")
        with open(os.path.join(tmpDir, ".gitignore"), "w") as f:
            f.write("*\n")
        generator_path = os.path.join(tmpDir, os.path.basename(DOTNET_GENERATOR_URL))
        download(DOTNET_GENERATOR_URL, generator_path)
        source_archive_path = os.path.join(tmpDir, os.path.basename(source_archive_url))
        download(source_archive_url, source_archive_path)
        source_path = os.path.join(tmpDir, "source")
        with tarfile.open(source_archive_path) as tar:
            tar.extractall(source_path)
        nuget_sources = []
        for arch, dotnet_arch in ARCHITECTURES:
            print(f"Architecture {arch}", file=sys.stderr)
            arch_nuget_sources_path = os.path.join(tmpDir, f"nuget-sources-{arch}.json")
            subprocess.run(
                [
                    sys.executable,
                    generator_path,
                    f"--freedesktop={runtime_version}",
                    f"--dotnet={dotnet_version}",
                    f"--runtime={dotnet_arch}",
                    arch_nuget_sources_path,
                    *DOTNET_PROJECTS,
                ],
                check=True,
                cwd=source_path,
            )
            with open(arch_nuget_sources_path, "rb") as f:
                arch_nuget_sources = json.load(f)
            if not arch_nuget_sources:
                raise Exception(f"No NuGet sources for {arch}")
            for src in arch_nuget_sources:
                src["only-arches"] = [arch]
                for existing_src in nuget_sources:
                    if existing_src["url"] == src["url"]:
                        existing_src["only-arches"].append(arch)
                        break
                else:
                    nuget_sources.append(src)
        for src in nuget_sources:
            src["only-arches"].sort()
            if all(arch in src["only-arches"] for arch, _ in ARCHITECTURES):
                del src["only-arches"]
        nuget_sources.sort(key=lambda src: src["dest-filename"])
        with open(NUGET_SOURCES_PATH, "w") as f:
            json.dump(nuget_sources, f, indent=4)


if __name__ == "__main__":
    main()
