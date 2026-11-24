#!/bin/bash
# Pipeline completo do vídeo "Lôri Kids — 5 anos".
# Uso: build.sh <pasta com os .mov originais> <pasta de trabalho>
# Requer: ffmpeg, python3 + numpy, skia-python, soundfile, opencv-python-headless<5
set -e
SRC=$1; WORK=$2; HERE=$(cd "$(dirname "$0")" && pwd); OUT=$HERE/../export
mkdir -p $WORK/raw $OUT
# 1) correção de cor individual + 30 fps constante
G1="colorbalance=rm=-0.025:gm=0.0:bm=0.01,eq=contrast=1.05:saturation=1.05:brightness=0.012"
G2="eq=contrast=1.04:saturation=1.04:brightness=-0.005"
G3="colorbalance=rs=-0.02:bs=0.03:rm=-0.03:bm=0.045:rh=-0.02:bh=0.05,eq=contrast=1.08:saturation=1.02:brightness=0.03"
G4="colorbalance=rh=-0.015:bh=0.05:bm=0.02,eq=contrast=1.05:saturation=0.94:gamma=0.96"
dec(){ ffmpeg -v error -y -i "$SRC/$1" -vf "$2,fps=30,scale=$3:flags=lanczos,format=rgb24" -f rawvideo $WORK/raw/$4.rgb
       ffmpeg -v error -y -i "$SRC/$1" -ac 1 -ar 48000 -c:a pcm_f32le $WORK/raw/$4.wav; }
dec IMG_2310.mov "$G1" 1440:2560 c1
dec IMG_2311.mov "$G2" 1440:2560 c2
dec copy_1A2C98C5-868B-47EB-A77D-83533818926B.mov "$G3" 1080:1920 c3
dec IMG_2323.mov "$G4" 1440:2560 c4
# 2) rastreamento do rosto (faces.json) — ver track_faces.py
python3 $HERE/track_faces.py "$SRC" "$WORK"
# 3) áudio editado + vídeo em 4 partes paralelas
LK_WORK=$WORK python3 $HERE/render.py audio $WORK/audio_raw.wav
for i in 0 1 2 3; do LK_WORK=$WORK python3 $HERE/render.py chunk $i 4 $WORK/chunk$i.mp4 & done; wait
printf "file '$WORK/chunk%d.mp4'\n" 0 1 2 3 > $WORK/list.txt
ffmpeg -v error -y -f concat -safe 0 -i $WORK/list.txt -c copy $WORK/video.mp4
# 4) masterização do áudio (-14 LUFS no estéreo final), mux e faststart
PRE="highpass=f=75,acompressor=threshold=-20dB:ratio=2.2:attack=8:release=120:makeup=1"
J=$(ffmpeg -hide_banner -i $WORK/audio_raw.wav -af "$PRE,loudnorm=I=-17:TP=-4.5:LRA=9:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
g(){ echo "$J" | python3 -c "import json,sys;print(json.load(sys.stdin)['$1'])"; }
ffmpeg -v error -y -i $WORK/audio_raw.wav -af "$PRE,loudnorm=I=-17:TP=-4.5:LRA=9:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,pan=stereo|c0=c0|c1=c0" -c:a pcm_s16le $WORK/audio.wav
ffmpeg -v error -y -i $WORK/video.mp4 -i $WORK/audio.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "$OUT/LoriKids_5anos_Reels_1080x1920.mp4"
