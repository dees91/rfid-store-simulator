#!/usr/bin/env bash
# Check the master, README GIF, and social preview against the output contract.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
video_dir="$(cd "${script_dir}/.." && pwd)"
repo_root="$(cd "${video_dir}/.." && pwd)"
master="${video_dir}/out/demo-master.mp4"
gif="${video_dir}/out/demo.gif"
social="${repo_root}/.github/assets/social-preview.png"

command -v ffprobe >/dev/null || { echo "ffprobe is required" >&2; exit 1; }
for f in "${master}" "${gif}" "${social}"; do test -f "$f" || { echo "Missing $f" >&2; exit 1; }; done

master_meta="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,nb_frames -of csv=p=0:s=x "${master}")"
test "${master_meta%x}" = "1920x1080x30/1x660" || { echo "Unexpected master metadata: ${master_meta}" >&2; exit 1; }
streams="$(ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "${master}")"
test "${streams%,}" = "video" || { echo "Master must be video-only: ${streams}" >&2; exit 1; }

gif_size="$(stat -f%z "${gif}")"
(( gif_size <= 10 * 1024 * 1024 )) || { echo "GIF exceeds 10 MiB: ${gif_size}" >&2; exit 1; }
gif_dims="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "${gif}")"

social_dims="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "${social}")"
test "${social_dims}" = "1280x640" || { echo "Unexpected social preview dimensions: ${social_dims}" >&2; exit 1; }
social_size="$(stat -f%z "${social}")"
(( social_size <= 1024 * 1024 )) || { echo "Social preview exceeds 1 MiB: ${social_size}" >&2; exit 1; }

echo "Verified master (${master_meta%x}), GIF (${gif_dims}, ${gif_size} bytes), social preview (${social_dims}, ${social_size} bytes)."
