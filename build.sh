#!/usr/bin/env bash
#
# build.sh — Build OpenWordnet-PT packages and Cygnet databases.
#
# Usage: bash build.sh [--rebuild] [--cygnet-only]
#   --rebuild      Wipe the cygnet work directory first (forces re-download of
#                  all wordnets — use when wordnets.toml URLs have changed)
#   --cygnet-only  Skip LMF generation and wn load test; just run the Cygnet
#                  database build and deploy docs/ (requires tarballs already
#                  in build/).  Combine with --rebuild to also clear cache.
#
# Produces:
#   build/own-pt-VERSION.tar.xz      — WN-LMF package (Portuguese)
#   build/own-en-VERSION.tar.xz      — WN-LMF package (English)
#   docs/pt-cygnet.db.gz             — Cygnet main database
#   docs/pt-provenance.db.gz         — Cygnet provenance database
#   docs/                            — web UI (serve with: bash run.sh)
#
# Prerequisites: uv, git, wget, xmlstarlet, python3

set -euo pipefail

VERSION="2026.04.07"
DTD="WN-LMF-1.4.dtd"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CYGNET_DIR="$(cd "$PROJECT_DIR/../cygnet" && pwd)"
CYGNET_WORK="$PROJECT_DIR/build/cygnet-work"

MODE="full"
for arg in "$@"; do
    case "$arg" in
        --rebuild)     rm -rf "$CYGNET_WORK"; echo "Cleaned cygnet work directory." ;;
        --cygnet-only) MODE="cygnet-only" ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

mkdir -p external build

if [[ "$MODE" == "full" ]]; then
# ── External dependencies ───────────────────────────────────────────────────
if [ ! -d external/cili ]; then
    echo "Retrieving ILI map"
    git clone https://github.com/globalwordnet/cili.git external/cili
fi

if [ ! -f "external/${DTD}" ]; then
    echo "Retrieving DTD"
    wget "https://globalwordnet.github.io/schemas/${DTD}" -O "external/${DTD}"
fi

# ── Python environment ────────────────────────────────────────────────────────
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt

ILI_MAP="$PROJECT_DIR/external/cili/ili-map.ttl"

# ── Build WN-LMF XML for each lexicon ────────────────────────────────────────
build_lmf() {
    local lang="$1"       # pt or en
    local lexicon_id="$2" # own-pt or own-en
    local label="$3"
    local raw_xml="build/${lexicon_id}-raw.xml"
    local fixed_xml="build/${lexicon_id}-${VERSION}.xml"

    echo "Building ${lexicon_id} LMF XML"
    python3 -m pyown.cli.lmf \
        data/own-${lang}-* \
        "$ILI_MAP" \
        -li "${lexicon_id}" \
        -lb "${label}" \
        -vr "${VERSION}" \
        -lg "${lang}" \
        -cs "1.0" \
        --status "checked" \
        --email "arademaker@gmail.com" \
        --url "https://github.com/omwn/openWordnet-PT" \
        --licence "https://creativecommons.org/licenses/by/4.0/" \
        --citation "Rademaker et al. (2012) OpenWordnet-PT: An Open Brazilian Wordnet for Reasoning. COLING 2012." \
        -o "${raw_xml}"

    echo "Fixing hypernym/hyponym direction and upgrading to LMF 1.4"
    python3 fix_lmf.py "${raw_xml}" "${fixed_xml}"
    rm -f "${raw_xml}" log-format
}

build_lmf "pt" "own-pt" "OpenWordnet-PT"
build_lmf "en" "own-en" "OpenWordnet-EN"

# ── Validate ──────────────────────────────────────────────────────────────────
echo "Validating"
xmlstarlet val -e -d "external/${DTD}" "build/own-pt-${VERSION}.xml"
xmlstarlet val -e -d "external/${DTD}" "build/own-en-${VERSION}.xml"

# ── Package per wordnet-release convention ────────────────────────────────────
package_wn() {
    local lexicon_id="$1"   # own-pt or own-en
    local pkg_dir="build/${lexicon_id}"

    echo "Packaging ${lexicon_id}"
    mkdir -p "${pkg_dir}"
    cp "build/${lexicon_id}-${VERSION}.xml" "${pkg_dir}/${lexicon_id}-${VERSION}.xml"
    cp README.md                            "${pkg_dir}/README.md"
    cp LICENSE                              "${pkg_dir}/LICENSE"
    cp etc/citation.bib                     "${pkg_dir}/citation.bib"
    tar -C build -cJf "build/${lexicon_id}-${VERSION}.tar.xz" "${lexicon_id}"
    echo "  build/${lexicon_id}-${VERSION}.tar.xz"
}

package_wn "own-pt"
package_wn "own-en"

# ── Validate with wn ──────────────────────────────────────────────────────────
echo "Testing wn load"
WN_TMPDIR="$(mktemp -d)"
trap 'rm -rf "$WN_TMPDIR"' EXIT
tar -xJf "build/own-pt-${VERSION}.tar.xz" -C "$WN_TMPDIR"
tar -xJf "build/own-en-${VERSION}.tar.xz" -C "$WN_TMPDIR"
uv run python - <<PYEOF
import wn
wn.config.data_home = "$WN_TMPDIR"
wn.add("$WN_TMPDIR/own-pt/own-pt-${VERSION}.xml")
wn.add("$WN_TMPDIR/own-en/own-en-${VERSION}.xml")
for lang, min_words in [("pt", 1000), ("en", 1000)]:
    lexs = wn.lexicons(lang=lang)
    assert lexs, f"No lexicons loaded for {lang}"
    n_words = len(wn.words(lang=lang))
    assert n_words > min_words, f"Too few words for {lang}: {n_words}"
    print(f"  {lang}: {len(lexs)} lexicon(s), {n_words} words")
PYEOF
echo "wn load test passed."

fi  # end MODE == full

# ── Cygnet database build ────────────────────────────────────────────────────
if [[ "$MODE" == "cygnet-only" ]]; then
    for pkg in "own-pt" "own-en"; do
        tarball="build/${pkg}-${VERSION}.tar.xz"
        extracted_xml="build/${pkg}/${pkg}-${VERSION}.xml"
        [[ -f "$tarball" ]] || {
            echo "Error: $tarball not found — run without --cygnet-only first." >&2
            exit 1
        }
        mkdir -p "build/${pkg}"
        if ! tar -xJf "$tarball" -C build/ "${pkg}/${pkg}-${VERSION}.xml" 2>/dev/null; then
            echo "Error: failed to extract ${pkg}/${pkg}-${VERSION}.xml from $tarball. Check that the tarball version and layout are correct." >&2
            exit 1
        fi
        [[ -f "$extracted_xml" ]] || {
            echo "Error: expected extracted file $extracted_xml was not found after unpacking $tarball." >&2
            exit 1
        }
    done
fi
echo ""
echo "=== Building Cygnet databases ==="

mkdir -p "$CYGNET_WORK/bin/raw_wns"
cp "$PROJECT_DIR/etc/wordnets.toml" "$CYGNET_WORK/wordnets.toml"
cp "$PROJECT_DIR/build/own-pt/own-pt-${VERSION}.xml" \
   "$CYGNET_WORK/bin/raw_wns/own-pt-${VERSION}.xml"
cp "$PROJECT_DIR/build/own-en/own-en-${VERSION}.xml" \
   "$CYGNET_WORK/bin/raw_wns/own-en-${VERSION}.xml"

bash "$CYGNET_DIR/build.sh" --work-dir "$(realpath "$CYGNET_WORK")"

# ── Deploy docs/ ──────────────────────────────────────────────────────────────
echo "Deploying to docs/"
mkdir -p "$PROJECT_DIR/docs"
cp "$CYGNET_DIR/web/index.html"          "$PROJECT_DIR/docs/"
cp "$CYGNET_DIR/web/relations.json"      "$PROJECT_DIR/docs/"
cp -r "$CYGNET_DIR/web/img"             "$PROJECT_DIR/docs/"
cp "$PROJECT_DIR/etc/local.json"         "$PROJECT_DIR/docs/"
cp "$PROJECT_DIR/logo/ownpt-baselogo.png" "$PROJECT_DIR/docs/"
touch "$PROJECT_DIR/docs/.nojekyll"
cp "$CYGNET_WORK/web/cygnet.db.gz"       "$PROJECT_DIR/docs/pt-cygnet.db.gz"
cp "$CYGNET_WORK/web/provenance.db.gz"   "$PROJECT_DIR/docs/pt-provenance.db.gz"

echo ""
echo "=== Build complete ==="
echo "  build/own-pt-${VERSION}.tar.xz  — Portuguese WN package"
echo "  build/own-en-${VERSION}.tar.xz  — English WN package"
echo "  docs/pt-cygnet.db.gz             — Cygnet main database"
echo "  docs/pt-provenance.db.gz         — Cygnet provenance database"
echo "  docs/                            — web UI (run with: bash run.sh)"
