#!/bin/bash

set -euo pipefail

readonly NAME="foundry.sh"
readonly REPO="SigNoz/foundry"
readonly BINARY="foundryctl"

FOUNDRY_VERSION="${FOUNDRY_VERSION:-}"
FOUNDRY_INSTALL_DIR="${FOUNDRY_INSTALL_DIR:-}"
FOUNDRY_ASSUME_YES="${FOUNDRY_ASSUME_YES:-false}"

if [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  readonly C_INFO=$'\033[32;1m'
  readonly C_WARN=$'\033[33;1m'
  readonly C_ERROR=$'\033[31;1m'
  readonly C_RESET=$'\033[0m'
else
  readonly C_INFO=""
  readonly C_WARN=""
  readonly C_ERROR=""
  readonly C_RESET=""
fi

info() {
  echo "${C_INFO}[INFO]${C_RESET} $*"
}

warn() {
  echo "${C_WARN}[WARN]${C_RESET} $*" >&2
}

err() {
  echo "${C_ERROR}[ERROR]${C_RESET} $*" >&2
}

die() {
  err "$*"
  exit 1
}

help() {
  printf "NAME\n"
  printf "\t%s - Install %s, the SigNoz Foundry CLI\n\n" "${NAME}" "${BINARY}"
  printf "USAGE\n"
  printf "\t%s [-v version] [-d directory] [-y] [-h]\n\n" "${NAME}"
  printf "DESCRIPTION\n"
  printf "\tDownloads, verifies, and installs the %s binary from GitHub releases.\n\n" "${BINARY}"
  printf "OPTIONS\n"
  printf "\t-v <version>\tVersion to install (e.g. v0.1.4). [env: FOUNDRY_VERSION] [default: latest]\n"
  printf "\t-d <path>\tInstall directory. [env: FOUNDRY_INSTALL_DIR] [default: \$XDG_BIN_HOME or ~/.local/bin]\n"
  printf "\t-y\t\tAuto-confirm upgrade prompt. [env: FOUNDRY_ASSUME_YES]\n"
  printf "\t-h\t\tShow this help message.\n\n"
  printf "EXAMPLES\n"
  printf "\t%s -v v0.1.4\n" "${NAME}"
  printf "\t%s -d /usr/local/bin\n" "${NAME}"
  printf "\tcurl -fsSL https://signoz.io/foundry.sh | bash\n"
  printf "\tcurl -fsSL https://signoz.io/foundry.sh | FOUNDRY_VERSION=v0.1.4 bash\n"
}

init_platform() {
  local raw_arch raw_os
  raw_arch="$(uname -m)"
  case "${raw_arch}" in
    x86_64 | amd64) PLATFORM_ARCH="amd64" ;;
    aarch64 | arm64) PLATFORM_ARCH="arm64" ;;
    *) die "Unsupported architecture: ${raw_arch}" ;;
  esac

  raw_os="$(uname | tr '[:upper:]' '[:lower:]')"
  PLATFORM_BIN_SUFFIX=""
  case "${raw_os}" in
    darwin | linux) PLATFORM_OS="${raw_os}" ;;
    mingw* | cygwin* | msys*)
      PLATFORM_OS="windows"
      PLATFORM_BIN_SUFFIX=".exe"
      ;;
    *) die "Unsupported operating system: ${raw_os}" ;;
  esac
}

verify_prereqs() {
  HAS_CURL="$(command -v curl >/dev/null 2>&1 && echo true || echo false)"
  HAS_WGET="$(command -v wget >/dev/null 2>&1 && echo true || echo false)"
  if [[ "${HAS_CURL}" != "true" ]] && [[ "${HAS_WGET}" != "true" ]]; then
    die "Missing prerequisite: curl or wget"
  fi
  local cmd
  for cmd in tar mktemp install; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      die "Missing prerequisite: ${cmd}"
    fi
  done
  if command -v sha256sum >/dev/null 2>&1; then
    SHA256_CMD="sha256sum"
  elif command -v shasum >/dev/null 2>&1; then
    SHA256_CMD="shasum -a 256"
  else
    die "Missing prerequisite: sha256sum or shasum"
  fi
}

fetch() {
  local url="$1"
  local out="$2"
  local mode="${3:-quiet}"
  if [[ "${HAS_CURL}" == "true" ]]; then
    if [[ "${mode}" == "progress" ]] && [[ -t 2 ]]; then
      curl -fL --progress-bar "${url}" -o "${out}"
    else
      curl -fsSL "${url}" -o "${out}"
    fi
  else
    if [[ "${mode}" == "progress" ]] && [[ -t 2 ]]; then
      wget -q --show-progress -O "${out}" "${url}"
    else
      wget -q -O "${out}" "${url}"
    fi
  fi
}

fetch_effective_url() {
  local url="$1"
  if [[ "${HAS_CURL}" == "true" ]]; then
    curl -sIL -o /dev/null -w '%{url_effective}' "${url}"
  else
    wget --max-redirect=5 --server-response --spider "${url}" 2>&1 \
      | awk '/^  Location: /{u=$2} END{print u}'
  fi
}

resolve_version() {
  if [[ -n "${FOUNDRY_VERSION}" ]]; then
    case "${FOUNDRY_VERSION}" in
      v*) TAG="${FOUNDRY_VERSION}" ;;
      *) TAG="v${FOUNDRY_VERSION}" ;;
    esac
  else
    local latest_url="https://github.com/${REPO}/releases/latest"
    local resolved
    resolved="$(fetch_effective_url "${latest_url}")"
    TAG="${resolved##*/tag/}"
    if [[ -z "${TAG}" ]] || [[ "${TAG}" == "${resolved}" ]]; then
      die "Could not resolve latest release tag from ${latest_url}"
    fi
  fi

  if [[ ! "${TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    die "Invalid version: ${TAG} (expected vMAJOR.MINOR.PATCH)"
  fi
}

resolve_install_dir() {
  if [[ -n "${FOUNDRY_INSTALL_DIR}" ]]; then
    INSTALL_DIR="${FOUNDRY_INSTALL_DIR}"
  elif [[ -n "${XDG_BIN_HOME:-}" ]]; then
    INSTALL_DIR="${XDG_BIN_HOME}"
  else
    INSTALL_DIR="${HOME}/.local/bin"
  fi
  mkdir -p "${INSTALL_DIR}"
  if [[ ! -w "${INSTALL_DIR}" ]]; then
    err "Install directory is not writable: ${INSTALL_DIR}"
    die "Set FOUNDRY_INSTALL_DIR to a writable path or run with appropriate permissions."
  fi
  DEST="${INSTALL_DIR}/${BINARY}${PLATFORM_BIN_SUFFIX}"
}

check_existing() {
  if [[ ! -f "${DEST}" ]]; then
    return
  fi
  local current
  current="$("${DEST}" version 2>/dev/null | awk '/^[[:space:]]*Version:/ {print $NF; exit}' || true)"
  if [[ -z "${current}" ]]; then
    return
  fi
  if [[ "${current}" == "${TAG}" ]]; then
    info "${BINARY} ${TAG} is already installed at ${DEST}"
    exit 0
  fi
  if [[ "${FOUNDRY_ASSUME_YES}" == "true" ]] || [[ ! -t 0 ]]; then
    info "Updating ${BINARY} ${current} -> ${TAG}"
    return
  fi
  local answer
  read -r -p "Update ${BINARY} ${current} to ${TAG}? [Y/n] " answer
  case "${answer}" in
    "" | y | Y | yes | YES) ;;
    *) die "Aborted by user" ;;
  esac
}

compute_release_artifacts() {
  TARBALL="foundry_${PLATFORM_OS}_${PLATFORM_ARCH}.tar.gz"
  CHECKSUMS="foundry_${TAG#v}_checksums.txt"
  TARBALL_URL="https://github.com/${REPO}/releases/download/${TAG}/${TARBALL}"
  CHECKSUMS_URL="https://github.com/${REPO}/releases/download/${TAG}/${CHECKSUMS}"
}

download_release() {
  TMP_ROOT="$(mktemp -d -t foundry-installer-XXXXXX)"
  TARBALL_PATH="${TMP_ROOT}/${TARBALL}"
  CHECKSUMS_PATH="${TMP_ROOT}/${CHECKSUMS}"

  info "Downloading ${TARBALL_URL}"
  fetch "${TARBALL_URL}" "${TARBALL_PATH}" progress
  fetch "${CHECKSUMS_URL}" "${CHECKSUMS_PATH}"
}

verify_checksum() {
  local expected
  expected="$(awk -v f="${TARBALL}" '$2 == f || $2 == "*"f {print $1; exit}' "${CHECKSUMS_PATH}")"
  if [[ -z "${expected}" ]]; then
    die "Checksum for ${TARBALL} not found in ${CHECKSUMS}"
  fi

  local actual
  actual="$(${SHA256_CMD} "${TARBALL_PATH}" | awk '{print $1}')"

  if [[ "${expected}" != "${actual}" ]]; then
    err "Checksum mismatch for ${TARBALL}"
    err "  expected: ${expected}"
    die "  actual:   ${actual}"
  fi
}

install_binary() {
  local extract_dir="${TMP_ROOT}/extract"
  mkdir -p "${extract_dir}"
  tar -xzf "${TARBALL_PATH}" -C "${extract_dir}"

  local src="${extract_dir}/foundry_${PLATFORM_OS}_${PLATFORM_ARCH}/bin/${BINARY}${PLATFORM_BIN_SUFFIX}"
  if [[ ! -f "${src}" ]]; then
    die "Expected binary not found in tarball: ${src#"${extract_dir}"/}"
  fi

  install -m 0755 "${src}" "${DEST}"
  info "Installed ${BINARY}${PLATFORM_BIN_SUFFIX} ${TAG} to ${DEST}"
}

verify_install() {
  local output
  if ! output="$("${DEST}" version 2>&1)"; then
    err "Installed binary failed to run: ${DEST}"
    err "This may indicate a wrong-arch download or a permissions issue."
    die "${output}"
  fi
  echo
  echo "${output}"
}

print_path_hint() {
  case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) return ;;
    *) ;;
  esac

  local rc_file
  case "${SHELL:-}" in
    */zsh) rc_file='~/.zshrc' ;;
    */bash) rc_file='~/.bashrc (Linux) or ~/.bash_profile (macOS)' ;;
    */fish) rc_file='~/.config/fish/config.fish' ;;
    *) rc_file='your shell config' ;;
  esac

  echo
  warn "${INSTALL_DIR} is not on your PATH."
  echo "To use ${BINARY} from any shell, add this to ${rc_file}:"
  echo
  echo "    export PATH=\"${INSTALL_DIR}:\$PATH\""
}

cleanup() {
  if [[ -n "${TMP_ROOT:-}" ]] && [[ -d "${TMP_ROOT}" ]]; then
    rm -rf "${TMP_ROOT}"
  fi
}

fail_trap() {
  local rc=$?
  if [[ ${rc} -ne 0 ]]; then
    err "Failed to install ${BINARY}."
    err "For support, see https://github.com/${REPO}/issues"
  fi
  cleanup
  exit "${rc}"
}

run() {
  init_platform
  verify_prereqs
  resolve_version
  resolve_install_dir
  check_existing
  compute_release_artifacts
  download_release
  verify_checksum
  install_binary
  verify_install
  print_path_hint
  cleanup
}

trap fail_trap EXIT

while getopts 'v:d:yh' opt; do
  case "${opt}" in
    v) FOUNDRY_VERSION="${OPTARG:-}" ;;
    d) FOUNDRY_INSTALL_DIR="${OPTARG:-}" ;;
    y) FOUNDRY_ASSUME_YES="true" ;;
    h)
      help
      trap - EXIT
      exit 0
      ;;
    ?) die "Invalid option: -${OPTARG:-}" ;;
    *) die "Unknown error while processing options" ;;
  esac
done

run
trap - EXIT
