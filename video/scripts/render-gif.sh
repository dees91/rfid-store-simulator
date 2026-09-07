#!/usr/bin/env bash
# Convert the rendered master into the README GIF (infinite loop, <= 10 MiB).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
video_dir="$(cd "${script_dir}/.." && pwd)"
repo_root="$(cd "${video_dir}/.." && pwd)"
input="${video_dir}/out/demo-master.mp4"
output="${video_dir}/out/demo.gif"
limit_bytes=$((10 * 1024 * 1024))

command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 1; }
test -f "${input}" || { echo "Render the master first: npm run render" >&2; exit 1; }
mkdir -p "$(dirname "${output}")"

render_gif() {
  local fps="$1" size="$2" colors="$3"
  ffmpeg -hide_banner -loglevel warning -y -i "${input}" \
    -filter_complex "fps=${fps},scale=${size}:flags=lanczos,split[s][p];[p]palettegen=max_colors=${colors}:stats_mode=diff[pal];[s][pal]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
    -loop 0 "${output}"
}

render_gif 12 "960:540" 192
if (( $(stat -f%z "${output}") > limit_bytes )); then render_gif 12 "960:540" 160; fi
if (( $(stat -f%z "${output}") > limit_bytes )); then render_gif 12 "864:486" 160; fi
if (( $(stat -f%z "${output}") > limit_bytes )); then
  echo "Unable to keep ${output} under 10 MiB without changing the storyboard." >&2
  exit 1
fi
echo "Wrote ${output} ($(stat -f%z "${output}") bytes)."
