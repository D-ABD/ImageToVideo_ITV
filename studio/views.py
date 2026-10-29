import json
from pathlib import Path
import threading

import pymupdf as fitz
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from .models import Scene, VideoProject, Voice

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 80
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png"}
ALLOWED_VOICES = {".wav", ".mp3", ".webm", ".m4a", ".ogg"}


def _check_upload(upload, extensions):
    if not upload or upload.size == 0:
        raise ValueError("Le fichier est vide.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValueError("Le fichier dépasse la limite de 50 Mo.")
    suffix = Path(upload.name).suffix.lower()
    if suffix not in extensions:
        raise ValueError("Format de fichier non pris en charge.")
    return suffix


def _image_scene(project, upload, position, page_number=1):
    try:
        upload.seek(0)
        with Image.open(upload) as im:
            im.verify()
        upload.seek(0)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Cette image ne peut pas être lue.") from exc
    return Scene.objects.create(project=project, image=upload, position=position, page_number=page_number)


def home(request):
    projects = VideoProject.objects.order_by("-updated_at")
    selected = projects.first()
    if selected:
        return redirect("project_detail", project_id=selected.id)
    voices = Voice.objects.order_by("-created_at")
    return render(request, "studio/home.html", {"projects": projects, "voices": voices, "project": None})


@require_POST
def create_project(request):
    files = request.FILES.getlist("source_files")
    title = (request.POST.get("title") or "Nouveau projet").strip()[:120] or "Nouveau projet"
    project = VideoProject.objects.create(title=title)
    if not files:
        return redirect("project_detail", project_id=project.id)
    position = 0
    try:
        for uploaded in files:
            suffix = _check_upload(uploaded, ALLOWED_IMAGES | {".pdf"})
            if suffix == ".pdf":
                data = uploaded.read()
                try:
                    pdf = fitz.open(stream=data, filetype="pdf")
                    if pdf.page_count > MAX_PDF_PAGES:
                        raise ValueError(f"Le PDF dépasse {MAX_PDF_PAGES} pages.")
                    if pdf.page_count == 0:
                        raise ValueError("Le PDF ne contient aucune page.")
                    for page_index, page in enumerate(pdf, start=1):
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                        scene = Scene(project=project, position=position, page_number=page_index)
                        scene.image.save(f"scene-{project.id}-{position + 1}.png", ContentFile(pix.tobytes("png")), save=False)
                        scene.save()
                        position += 1
                except (fitz.FileDataError, RuntimeError) as exc:
                    raise ValueError("Le PDF est illisible ou protégé par mot de passe.") from exc
            else:
                _image_scene(project, uploaded, position)
                position += 1
        if position == 0:
            raise ValueError("Aucune scène n’a pu être créée.")
    except Exception as exc:
        project.delete()
        messages.error(request, str(exc) or "Impossible d’importer ce fichier.")
        return redirect("home")
    return redirect("project_detail", project_id=project.id)


def project_detail(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    scenes = list(project.scenes.all())
    requested_scene = request.GET.get("scene")
    selected_scene = next((s for s in scenes if str(s.id) == requested_scene), scenes[0] if scenes else None)
    voices = Voice.objects.order_by("-created_at")
    return render(request, "studio/project.html", {
        "project": project, "projects": VideoProject.objects.order_by("-updated_at"),
        "scenes": scenes, "selected_scene": selected_scene, "voices": voices,
        "motion_choices": Scene.MOTION_CHOICES,
    })


@require_POST
def save_scene(request, project_id, scene_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    scene = get_object_or_404(Scene, pk=scene_id, project=project)
    narration_text = request.POST.get("narration_text", "")[:12000].strip()
    motion = request.POST.get("motion")
    try:
        motion_amount = int(request.POST.get("motion_amount", scene.motion_amount))
    except (TypeError, ValueError):
        motion_amount = scene.motion_amount
    motion_amount = max(5, min(60, motion_amount))
    changed = narration_text != scene.narration_text or motion_amount != scene.motion_amount
    if motion in dict(Scene.MOTION_CHOICES) and motion != scene.motion:
        scene.motion = motion
        changed = True
    if changed:
        scene.narration_text = narration_text
        scene.motion_amount = motion_amount
        scene.save(update_fields=["narration_text", "motion", "motion_amount", "updated_at"])
        project.status = "draft"
        if project.video:
            project.video.delete(save=False)
        project.video = ""
        project.save(update_fields=["status", "video", "updated_at"])
    messages.success(request, "Scène enregistrée.")
    return redirect(f"/projects/{project.id}/?scene={scene.id}")


@require_POST
def reorder_scenes(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    try:
        ids = json.loads(request.body).get("scene_ids", [])
    except (json.JSONDecodeError, AttributeError):
        return HttpResponseBadRequest("Ordre de scènes invalide.")
    actual = set(project.scenes.values_list("id", flat=True))
    if set(ids) != actual or len(ids) != len(actual):
        return HttpResponseBadRequest("La liste ne correspond pas aux scènes du projet.")
    for index, scene_id in enumerate(ids):
        Scene.objects.filter(project=project, id=scene_id).update(position=index)
    return JsonResponse({"ok": True})


@require_POST
def delete_scene(request, project_id, scene_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    scene = get_object_or_404(Scene, pk=scene_id, project=project)
    scene.delete()
    for index, remaining in enumerate(project.scenes.order_by("position", "id")):
        if remaining.position != index:
            Scene.objects.filter(pk=remaining.pk).update(position=index)
    project.status = "draft"
    if project.video:
        project.video.delete(save=False)
    project.video = ""
    project.save(update_fields=["status", "video", "updated_at"])
    return redirect("project_detail", project_id=project.id)


@require_POST
def create_voice(request):
    upload = request.FILES.get("sample")
    name = (request.POST.get("name") or "").strip()[:80]
    if not name:
        messages.error(request, "Donne un nom à cette voix.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    if request.POST.get("voice_consent") != "on":
        messages.error(request, "Confirme que tu es autorisé·e à cloner cette voix.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
    try:
        suffix = _check_upload(upload, ALLOWED_VOICES)
        # A browser recording is sent as WebM. Convert it to WAV locally for playback and XTTS.
        if suffix != ".wav":
            from .pipeline import convert_audio_to_wav
            converted = convert_audio_to_wav(upload)
            voice = Voice(name=name, consent_confirmed=True)
            voice.sample.save(f"voice-{name[:24]}.wav", ContentFile(converted), save=False)
            voice.save()
        else:
            voice = Voice(name=name, sample=upload, consent_confirmed=True)
            voice.save()
        messages.success(request, f"La voix « {voice.name} » a été enregistrée sur cet appareil.")
    except Exception as exc:
        messages.error(request, str(exc) or "Impossible d’enregistrer cet échantillon vocal.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@require_POST
def generate(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    if project.status in {"preparing", "processing"}:
        return JsonResponse({"ok": False, "error": "Un traitement est déjà en cours."}, status=409)
    voice_id = request.POST.get("voice_id")
    voice = get_object_or_404(Voice, pk=voice_id, consent_confirmed=True) if voice_id else None
    scenes = list(project.scenes.all())
    if not scenes or any(not scene.narration_text.strip() for scene in scenes):
        return JsonResponse({"ok": False, "error": "Ajoute un texte à chaque scène avant de générer la vidéo."}, status=400)
    if not voice:
        return JsonResponse({"ok": False, "error": "Choisis une voix enregistrée avec son autorisation."}, status=400)
    ratio = request.POST.get("ratio", "9:16")
    if ratio not in dict(VideoProject.FORMAT_CHOICES):
        return JsonResponse({"ok": False, "error": "Format vidéo invalide."}, status=400)
    project.selected_voice = voice
    project.ratio = ratio
    project.subtitles_enabled = request.POST.get("subtitles_enabled") == "on"
    project.status = "processing"
    project.status_message = "Préparation du traitement…"
    project.progress_percent = 0
    project.error_message = ""
    project.save()
    thread = threading.Thread(target=_run_generation, args=(project.id,), daemon=True)
    thread.start()
    return JsonResponse({"ok": True, "status_url": f"/projects/{project.id}/status/"})


@require_POST
def prepare_audio(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    if project.status in {"preparing", "processing"}:
        return JsonResponse({"ok": False, "error": "Un traitement est déjà en cours."}, status=409)
    voice_id = request.POST.get("voice_id")
    voice = get_object_or_404(Voice, pk=voice_id, consent_confirmed=True) if voice_id else None
    scenes = list(project.scenes.all())
    if not scenes or any(not scene.narration_text.strip() for scene in scenes):
        return JsonResponse({"ok": False, "error": "Ajoute un texte à chaque scène avant de préparer la narration."}, status=400)
    if not voice:
        return JsonResponse({"ok": False, "error": "Choisis une voix enregistrée avec son autorisation."}, status=400)
    if project.selected_voice_id != voice.pk and project.video:
        project.video.delete(save=False)
        project.video = ""
    project.selected_voice = voice
    project.status = "preparing"
    project.status_message = "Préparation de la narration…"
    project.progress_percent = 0
    project.error_message = ""
    project.save()
    thread = threading.Thread(target=_run_audio_preparation, args=(project.id,), daemon=True)
    thread.start()
    return JsonResponse({"ok": True, "status_url": f"/projects/{project.id}/status/"})


def _run_audio_preparation(project_id):
    from .pipeline import prepare_project_audio
    try:
        project = VideoProject.objects.get(pk=project_id)
        prepare_project_audio(project)
    except Exception as exc:
        VideoProject.objects.filter(pk=project_id).update(
            status="error", status_message="La préparation audio a échoué.",
            error_message=str(exc)[:1200],
        )


def _run_generation(project_id):
    from .pipeline import build_project_video
    try:
        project = VideoProject.objects.get(pk=project_id)
        build_project_video(project)
    except Exception as exc:
        VideoProject.objects.filter(pk=project_id).update(status="error", status_message="La génération a échoué.", error_message=str(exc)[:1200])


def project_status(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    scene_id = request.GET.get("scene")
    scene = (project.scenes.filter(pk=scene_id).first() if scene_id else None) or project.scenes.first()
    return JsonResponse({
        "status": project.status, "message": project.status_message,
        "error": project.error_message,
        "progress": project.progress_percent,
        "video_url": project.video.url if project.video else "",
        "audio_url": scene.audio.url if scene and scene.audio else "",
    })
