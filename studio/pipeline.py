"""Local XTTS → WhisperX forced alignment → FFmpeg pipeline."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

import certifi
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Scene, VideoProject

_TTS = None
_TTS_LOCK = threading.Lock()
_ALIGN_LOCK = threading.Lock()

os.environ.setdefault("SSL_CERT_FILE", certifi.where())


def _ffmpeg_path():
    candidates = [
        os.environ.get("FFMPEG_BINARY"),
        "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
        shutil.which("ffmpeg"),
    ]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    else:
        raise RuntimeError("FFmpeg n’a pas été trouvé. Installe-le puis relance le serveur Django.")


def _supports_subtitles_filter(ffmpeg):
    result = subprocess.run([ffmpeg, "-filters"], capture_output=True, text=True)
    return not result.returncode and any(
        " subtitles " in f" {line} " for line in result.stdout.splitlines()
    )


def _subtitle_font(size):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _write_subtitle_overlay(caption, path, width, height):
    font_size = 42
    font = _subtitle_font(font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_text_width = width - 120
    lines, line = [], ""
    for word in caption["text"].split():
        candidate = f"{line} {word}".strip()
        if line and measure.textbbox((0, 0), candidate, font=font)[2] > max_text_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)

    line_height = font_size + 8
    padding_x, padding_y, margin_bottom = 24, 14, 58
    box_width = max(measure.textbbox((0, 0), text, font=font)[2] for text in lines) + padding_x * 2
    box_height = line_height * len(lines) + padding_y * 2
    left = (width - box_width) // 2
    top = height - margin_bottom - box_height
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (left, top, left + box_width, top + box_height),
        radius=12, fill=(0, 0, 0, 160),
    )
    for index, text in enumerate(lines):
        draw.text(
            (width // 2, top + padding_y + index * line_height), text,
            font=font, fill=(255, 255, 255, 255), anchor="ma",
        )
    image.save(path)


def _camera_filter(motion, motion_amount, ratio, duration):
    width, height = (720, 1280) if ratio == "9:16" else (1280, 720)
    fps = 25
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
    if motion == "still":
        return vf + f",fps={fps}", width, height, fps

    frame_count = max(1, round(duration * fps))
    amount = max(5, min(60, int(motion_amount))) / 100
    progress = f"min(on/{frame_count},1)"
    x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        zoom = f"1+{amount:.3f}*{progress}"
    elif motion == "zoom_out":
        zoom = f"1+{amount:.3f}*(1-{progress})"
    else:
        zoom = f"1+{amount:.3f}"
        max_x = "iw-iw/zoom"
        max_y = "ih-ih/zoom"
        if motion == "pan_left":
            x = f"({max_x})*(1-{progress})"
        elif motion == "pan_right":
            x = f"({max_x})*{progress}"
        elif motion == "pan_up":
            y = f"({max_y})*(1-{progress})"
        elif motion == "pan_down":
            y = f"({max_y})*{progress}"
    vf += f",zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={width}x{height}:fps={fps}"
    return vf, width, height, fps


def _ffmpeg_scene_with_overlay(ffmpeg, image_path, audio_path, captions, output_path, motion, motion_amount, ratio, duration):
    vf, width, height, fps = _camera_filter(motion, motion_amount, ratio, duration)

    with tempfile.TemporaryDirectory(prefix="coach-subtitles-") as folder:
        inputs = [ffmpeg, "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(image_path), "-i", str(audio_path)]
        filters = [f"[0:v]{vf}[base0]"]
        current = "base0"
        for index, caption in enumerate(captions):
            overlay_path = Path(folder) / f"caption-{index:04}.png"
            _write_subtitle_overlay(caption, overlay_path, width, height)
            inputs.extend(["-loop", "1", "-framerate", str(fps), "-i", str(overlay_path)])
            next_label = f"base{index + 1}"
            start = max(0, float(caption["start"]))
            end = max(start, float(caption["end"]))
            filters.append(
                f"[{current}][{index + 2}:v]overlay=0:0:format=auto:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
            )
            current = next_label
        inputs.extend([
            "-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", "1:a",
            "-t", f"{max(0.2, duration):.3f}", "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(output_path),
        ])
        run = subprocess.run(inputs, capture_output=True, text=True)
    if run.returncode or not output_path.exists():
        detail = (run.stderr or "").strip().splitlines()[-1:]
        raise RuntimeError("FFmpeg n’a pas pu assembler la scène. " + (detail[0] if detail else "Vérifie les codecs libx264 et AAC."))


def convert_audio_to_wav(upload):
    """Convert an uploaded/recorded sample to mono 24 kHz WAV using local FFmpeg."""
    ffmpeg = _ffmpeg_path()
    suffix = Path(upload.name or "sample.webm").suffix or ".webm"
    with tempfile.TemporaryDirectory(prefix="coach-voice-") as folder:
        source = Path(folder) / f"source{suffix}"
        target = Path(folder) / "sample.wav"
        upload.seek(0)
        source.write_bytes(upload.read())
        run = subprocess.run([
            ffmpeg, "-y", "-v", "error", "-i", str(source), "-ac", "1", "-ar", "24000", str(target),
        ], capture_output=True, text=True)
        if run.returncode or not target.exists():
            raise RuntimeError("Échantillon audio illisible. Essaie un WAV ou MP3 de quelques secondes.")
        return target.read_bytes()


def _get_tts():
    global _TTS
    if _TTS is None:
        with _TTS_LOCK:
            if _TTS is None:
                try:
                    import torch
                    from TTS.api import TTS
                except ImportError as exc:
                    raise RuntimeError("XTTS n’est pas installé. Suis l’étape 4 du README pour installer les dépendances IA.") from exc
                use_gpu = torch.cuda.is_available()
                _TTS = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)
    return _TTS


def _sample_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _synthesize(scene, voice, cache_key, destination):
    cache = Path(settings.MEDIA_ROOT) / "audio-cache" / f"{cache_key}.wav"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 1024:
        shutil.copy2(cache, destination)
        return
    model = _get_tts()
    model.tts_to_file(
        text=scene.narration_text,
        file_path=str(destination),
        speaker_wav=[voice.sample.path],
        language="fr",
        split_sentences=True,
    )
    if not destination.exists() or destination.stat().st_size < 1024:
        raise RuntimeError(f"XTTS n’a pas produit l’audio de la scène {scene.position + 1}.")
    shutil.copy2(destination, cache)


def _scene_audio_cache_key(scene, voice):
    key_source = f"{scene.narration_text.strip()}\0{_sample_digest(voice.sample.path)}\0xtts_v2\0fr"
    return hashlib.sha256(key_source.encode("utf-8")).hexdigest()


def _prepare_scene_audio(scene, voice, cache_key, audio_path, on_progress=None):
    if scene.cache_key == cache_key and scene.audio and scene.audio.name and scene.subtitle_data:
        shutil.copy2(scene.audio.path, audio_path)
        if on_progress:
            on_progress("Audio et sous-titres déjà prêts", 0.8)
        return scene.subtitle_data

    if on_progress:
        on_progress("Synthèse de la voix", 0.2)
    _synthesize(scene, voice, cache_key, audio_path)
    if on_progress:
        on_progress("Synchronisation des sous-titres", 0.62)
    captions = _align_and_caption(audio_path, scene.narration_text)
    scene.subtitle_data = captions
    scene.cache_key = cache_key
    scene.duration_seconds = max(caption["end"] for caption in captions)
    with audio_path.open("rb") as audio_file:
        scene.audio.save(f"scene-{scene.pk}-{cache_key[:12]}.wav", File(audio_file), save=False)
    scene.save(update_fields=["audio", "subtitle_data", "duration_seconds", "cache_key", "updated_at"])
    return captions


def prepare_project_audio(project):
    scenes = list(project.scenes.order_by("position", "id"))
    voice = project.selected_voice
    if not scenes or not voice or not voice.consent_confirmed:
        raise RuntimeError("Le projet doit avoir des scènes et une voix autorisée.")
    progress = lambda text, percent: VideoProject.objects.filter(pk=project.pk).update(
        status_message=text, progress_percent=percent,
    )
    with tempfile.TemporaryDirectory(prefix=f"coach-audio-{project.pk}-") as folder:
        for index, scene in enumerate(scenes, start=1):
            scene_count = len(scenes)
            scene_progress = lambda fraction: 5 + round(((index - 1 + fraction) / scene_count) * 90)
            cache_key = _scene_audio_cache_key(scene, voice)
            audio_path = Path(folder) / f"audio-{index:03}.wav"

            def update_progress(stage, fraction):
                progress(f"{stage} · scène {index}/{scene_count}", scene_progress(fraction))

            _prepare_scene_audio(scene, voice, cache_key, audio_path, update_progress)
    project.status = "prepared"
    project.status_message = "Narration et sous-titres prêts à écouter."
    project.progress_percent = 100
    project.error_message = ""
    project.save(update_fields=["status", "status_message", "progress_percent", "error_message", "updated_at"])


def _align_and_caption(audio_path, narration_text):
    """Forced-align the supplied script to generated speech and build progressive phrase captions."""
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError("WhisperX n’est pas installé. Suis l’étape 4 du README pour les dépendances IA.") from exc
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    audio = whisperx.load_audio(str(audio_path))
    model_a, metadata = whisperx.load_align_model(language_code="fr", device=device)
    try:
        # The authored narration is supplied as a transcript: this is forced alignment, not a fresh ASR pass.
        result = whisperx.align(
            [{"start": 0.0, "end": len(audio) / 16000.0, "text": narration_text}],
            model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        words = result.get("word_segments", [])
        captions = _group_words(words)
        if not captions:
            raise RuntimeError("Aucun sous-titre n’a pu être aligné sur la narration.")
        return captions
    finally:
        del model_a
        if device == "cuda":
            torch.cuda.empty_cache()


def _group_words(words, max_words=7):
    groups, current = [], []
    for item in words:
        word = (item.get("word") or "").strip()
        start, end = item.get("start"), item.get("end")
        if not word or start is None or end is None:
            continue
        current.append({"word": word, "start": float(start), "end": float(end)})
        if len(current) >= max_words or word.endswith((".", "?", "!", ":", ";")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [
        {"start": g[0]["start"], "end": g[-1]["end"], "text": " ".join(w["word"] for w in g)}
        for g in groups if g[-1]["end"] > g[0]["start"]
    ]


def _srt_timestamp(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _write_srt(captions, path):
    blocks = []
    for i, cap in enumerate(captions, start=1):
        blocks.append(f"{i}\n{_srt_timestamp(cap['start'])} --> {_srt_timestamp(cap['end'])}\n{cap['text']}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def _ffmpeg_scene(image_path, audio_path, srt_path, output_path, motion, motion_amount, ratio, duration, subtitles_enabled, captions=None, subtitles_filter_available=True):
    ffmpeg = _ffmpeg_path()
    if subtitles_enabled and not subtitles_filter_available:
        return _ffmpeg_scene_with_overlay(
            ffmpeg, image_path, audio_path, captions or [], output_path, motion, motion_amount, ratio, duration,
        )
    vf, width, height, fps = _camera_filter(motion, motion_amount, ratio, duration)
    if subtitles_enabled:
        # FFmpeg's subtitles filter/libass draws a dark semi-transparent box with bottom margins.
        safe_srt = str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        style = "FontName=Arial,FontSize=42,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BackColour=&H99000000,BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=58,MarginL=60,MarginR=60"
        vf += f",subtitles='{safe_srt}':force_style='{style}'"
    run = subprocess.run([
        ffmpeg, "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(image_path),
        "-i", str(audio_path), "-vf", vf, "-t", f"{max(0.2, duration):.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output_path),
    ], capture_output=True, text=True)
    if run.returncode or not output_path.exists():
        detail = (run.stderr or "").strip().splitlines()[-1:]
        raise RuntimeError("FFmpeg n’a pas pu assembler la scène. " + (detail[0] if detail else "Vérifie son installation avec les filtres libass."))


def build_project_video(project):
    scenes = list(project.scenes.order_by("position", "id"))
    voice = project.selected_voice
    if not scenes or not voice or not voice.consent_confirmed:
        raise RuntimeError("Le projet doit avoir des scènes et une voix autorisée.")
    subtitles_filter_available = (
        _supports_subtitles_filter(_ffmpeg_path()) if project.subtitles_enabled else False
    )
    def progress(text, percent):
        VideoProject.objects.filter(pk=project.pk).update(
            status_message=text, progress_percent=percent,
        )

    scene_clips = []
    with tempfile.TemporaryDirectory(prefix=f"coach-project-{project.pk}-") as folder:
        work = Path(folder)
        for index, scene in enumerate(scenes, start=1):
            scene_count = len(scenes)
            scene_progress = lambda fraction: 5 + round(((index - 1 + fraction) / scene_count) * 82)
            cache_key = _scene_audio_cache_key(scene, voice)
            audio_path = work / f"audio-{index:03}.wav"
            def update_audio_progress(stage, fraction):
                progress(f"{stage} · scène {index}/{scene_count}", scene_progress(fraction))

            captions = _prepare_scene_audio(
                scene, voice, cache_key, audio_path, update_audio_progress,
            )
            srt_path = work / f"scene-{index:03}.srt"
            _write_srt(captions, srt_path)
            clip_path = work / f"clip-{index:03}.mp4"
            progress(f"Assemblage de la scène · {index}/{scene_count}", scene_progress(0.82))
            _ffmpeg_scene(
                scene.image.path, audio_path, srt_path, clip_path, scene.motion, scene.motion_amount,
                project.ratio, scene.duration_seconds, project.subtitles_enabled, scene.subtitle_data,
                subtitles_filter_available,
            )
            scene_clips.append(clip_path)
            progress(f"Scène prête · {index}/{scene_count}", scene_progress(1))
        progress("Assemblage de la vidéo finale…", 92)
        concat_list = work / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in scene_clips), encoding="utf-8")
        final_path = work / "final.mp4"
        run = subprocess.run([
            _ffmpeg_path(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-movflags", "+faststart", str(final_path),
        ], capture_output=True, text=True)
        if run.returncode or not final_path.exists():
            raise RuntimeError("Impossible de réunir les scènes en MP4. " + (run.stderr or "").strip()[-500:])
        with final_path.open("rb") as video_file:
            project.video.save(f"projet-{project.pk}-{timezone.now():%Y%m%d-%H%M%S}.mp4", File(video_file), save=False)
    project.status = "ready"
    project.status_message = "Vidéo prête à prévisualiser et télécharger."
    project.progress_percent = 100
    project.error_message = ""
    project.save(update_fields=["video", "status", "status_message", "progress_percent", "error_message", "updated_at"])
