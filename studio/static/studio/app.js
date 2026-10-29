(() => {
  const text = document.querySelector('#narrationText');
  if (text) {
    const words = document.querySelector('#wordCount');
    const seconds = document.querySelector('#sceneDuration');
    const update = () => {
      const count = text.value.trim() ? text.value.trim().split(/\s+/).length : 0;
      words.textContent = count;
      seconds.textContent = count ? Math.max(1, Math.ceil(count / 2.35)) : 0;
    };
    text.addEventListener('input', update);
    update();
  }
  const motionSelect = document.querySelector('#motionSelect');
  if (motionSelect) {
    const controls = motionSelect.closest('.scene-controls');
    const strengthLabel = document.createElement('label');
    strengthLabel.className = 'select-label motion-strength';
    strengthLabel.style.cssText = 'display:grid;gap:6px';
    const strengthTitle = document.createElement('span');
    const strengthOutput = document.createElement('output');
    const strengthSlider = document.createElement('input');
    strengthSlider.type = 'range';
    strengthSlider.name = 'motion_amount';
    strengthSlider.min = '5';
    strengthSlider.max = '60';
    strengthSlider.step = '1';
    strengthSlider.value = String(Math.max(5, Math.min(60, Number(document.body.dataset.motionAmount) || 25)));
    strengthSlider.setAttribute('form', 'sceneForm');
    strengthSlider.setAttribute('aria-label', 'Intensité du mouvement');
    strengthSlider.style.cssText = 'width:100%;accent-color:#f4a15b';
    strengthTitle.append('Intensité du mouvement ', strengthOutput);
    strengthLabel.append(strengthTitle, strengthSlider);
    controls.insertBefore(strengthLabel, controls.querySelector('.motion-hint'));

    const hint = controls.querySelector('.motion-hint span:last-child');
    const descriptions = {
      still: 'Image fixe pendant toute la scène.',
      zoom_in: 'Zoom avant progressif pendant toute la scène.',
      zoom_out: 'Zoom arrière progressif pendant toute la scène.',
      pan_left: 'Le cadrage se déplace vers la gauche.',
      pan_right: 'Le cadrage se déplace vers la droite.',
      pan_up: 'Le cadrage se déplace vers le haut.',
      pan_down: 'Le cadrage se déplace vers le bas.',
    };
    const updateMotionControls = () => {
      strengthOutput.textContent = `${strengthSlider.value}%`;
      strengthLabel.hidden = motionSelect.value === 'still';
      hint.textContent = descriptions[motionSelect.value] || '';
    };
    motionSelect.addEventListener('change', updateMotionControls);
    strengthSlider.addEventListener('input', updateMotionControls);
    updateMotionControls();
  }
  const strip = document.querySelector('#sceneStrip');
  if (strip) {
    let dragged = null;
    strip.querySelectorAll('.scene-card').forEach(card => {
      card.addEventListener('dragstart', () => { dragged = card; card.classList.add('dragging'); });
      card.addEventListener('dragend', async () => {
        card.classList.remove('dragging');
        const ids = [...strip.querySelectorAll('.scene-card')].map(item => Number(item.dataset.id));
        const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        try {
          const response = await fetch(strip.dataset.reorderUrl, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({scene_ids:ids})});
          if (!response.ok) throw new Error('L’ordre n’a pas pu être sauvegardé.');
          const current = new URL(location.href).searchParams.get('scene');
          location.href = `?scene=${current || ids[0]}`;
        } catch (error) { alert(error.message); location.reload(); }
      });
      card.addEventListener('dragover', event => {
        event.preventDefault(); if (!dragged || dragged === card) return;
        const rect = card.getBoundingClientRect();
        strip.insertBefore(dragged, event.clientX > rect.left + rect.width / 2 ? card.nextSibling : card);
      });
    });
  }
  const fileInput = document.querySelector('input[name=sample]');
  const preview = document.querySelector('#samplePreview');
  if (fileInput && preview) fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0]; if (file) { preview.src = URL.createObjectURL(file); preview.hidden = false; }
  });
  const recordButton = document.querySelector('#recordButton');
  if (recordButton && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
    let recorder = null, chunks = [], stream = null;
    recordButton.addEventListener('click', async () => {
      const status = document.querySelector('#recordStatus');
      if (recorder?.state === 'recording') { recorder.stop(); recordButton.textContent = '● Enregistrer avec le micro'; return; }
      try {
        stream = await navigator.mediaDevices.getUserMedia({audio:true}); recorder = new MediaRecorder(stream); chunks = [];
        recorder.addEventListener('dataavailable', event => { if (event.data.size) chunks.push(event.data); });
        recorder.addEventListener('stop', () => {
          const blob = new Blob(chunks, {type:recorder.mimeType || 'audio/webm'});
          const file = new File([blob], 'ma-voix.webm', {type:blob.type});
          const transfer = new DataTransfer(); transfer.items.add(file); fileInput.files = transfer.files;
          preview.src = URL.createObjectURL(blob); preview.hidden = false;
          status.textContent = 'Enregistrement prêt. Écoute-le avant de sauvegarder.';
          stream?.getTracks().forEach(track => track.stop()); stream = null;
        });
        recorder.start(); recordButton.textContent = '■ Arrêter'; status.textContent = 'Enregistrement en cours…';
      } catch { status.textContent = 'Autorise le microphone ou importe un fichier WAV/MP3.'; }
    });
  } else if (recordButton) { recordButton.disabled = true; recordButton.title = 'Enregistrement non pris en charge dans ce navigateur.'; }
  const generateForm = document.querySelector('#generateForm');
  if (generateForm) {
    const button = document.querySelector('#generateButton');
    const status = document.querySelector('#jobStatus');
    const card = document.querySelector('.generate-card');
    const prepareButton = document.createElement('button');
    prepareButton.type = 'button';
    prepareButton.className = 'button button-secondary full prepare-audio-button';
    prepareButton.textContent = 'Préparer la narration';
    const preparedAudio = document.createElement('audio');
    preparedAudio.className = 'prepared-audio';
    preparedAudio.controls = true;
    preparedAudio.preload = 'none';
    preparedAudio.hidden = true;
    card.insertBefore(prepareButton, generateForm);
    card.insertBefore(preparedAudio, generateForm);
    const progress = document.createElement('progress');
    progress.className = 'job-progress';
    progress.max = 100;
    progress.value = Number(document.body.dataset.progressPercent) || 0;
    progress.hidden = !['preparing', 'prepared', 'processing', 'ready'].includes(document.body.dataset.projectStatus);
    progress.setAttribute('aria-label', 'Progression de la génération vidéo');
    progress.style.cssText = 'display:block;width:100%;height:9px;margin-top:12px;accent-color:#a9c99b';
    status.before(progress);
    const startedAt = Date.now();
    const elapsedLabel = () => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    };

    const showVideo = url => {
      let video = card.querySelector('.video-result');
      if (!video) {
        video = document.createElement('video');
        video.className = 'video-result';
        video.controls = true;
        video.playsInline = true;
        card.append(video);
      }
      video.src = url;
      let download = card.querySelector('.download');
      if (!download) {
        download = document.createElement('a');
        download.className = 'button button-secondary full download';
        download.textContent = 'Télécharger le MP4 ↓';
        card.append(download);
      }
      download.href = url;
      download.download = url.split('/').pop() || 'video.mp4';
    };

    const sceneStatusUrl = `/projects/${document.body.dataset.projectId}/status/?scene=${document.body.dataset.sceneId}`;
    const setBusy = busy => {
      button.disabled = busy;
      prepareButton.disabled = busy;
    };
    const saveCurrentScene = async () => {
      const sceneForm = document.querySelector('#sceneForm');
      if (!sceneForm) return;
      const response = await fetch(sceneForm.action, {method:'POST', body:new FormData(sceneForm)});
      if (!response.ok) throw new Error('Enregistre le texte de la scène avant le traitement.');
    };

    const pollStatus = async (url, mode, notificationPermission) => {
      try {
        const response = await fetch(url, {cache:'no-store'});
        if (!response.ok) throw new Error();
        const result = await response.json();
        progress.value = Math.max(0, Math.min(100, Number(result.progress) || 0));
        status.textContent = `${result.message || 'Traitement en cours…'} · ${progress.value}% · ${elapsedLabel()}`;
        if (mode === 'audio' && result.status === 'prepared') {
          progress.value = 100;
          status.className = 'job-status success';
          status.textContent = 'Narration prête. Tu peux écouter l’audio ou générer la vidéo.';
          if (result.audio_url) {
            preparedAudio.src = result.audio_url;
            preparedAudio.hidden = false;
          }
          document.body.dataset.projectStatus = 'prepared';
          prepareButton.textContent = 'Préparer la narration';
          setBusy(false);
          return;
        }
        if (result.status === 'ready') {
          progress.value = 100;
          status.className = 'job-status success';
          status.textContent = 'Vidéo terminée · 100%. Elle est prête à être lue ou téléchargée.';
          if (result.video_url) showVideo(result.video_url);
          prepareButton.textContent = 'Préparer la narration';
          setBusy(false);
          if (notificationPermission) notificationPermission.then(permission => {
            if (permission === 'granted') new Notification('Vidéo terminée', {body:'Ta vidéo est prête à être lue ou téléchargée.'});
          });
          return;
        }
        if (result.status === 'error') {
          status.className = 'job-status error';
          status.textContent = result.error || 'Une erreur est survenue.';
          prepareButton.textContent = 'Préparer la narration';
          setBusy(false);
          return;
        }
        window.setTimeout(() => pollStatus(url, mode, notificationPermission), 1500);
      } catch {
        status.className = 'job-status error';
        status.textContent = 'Impossible de lire l’état. Le traitement peut continuer en arrière-plan.';
        setBusy(false);
      }
    };

    const projectStatus = document.body.dataset.projectStatus;
    if (projectStatus === 'preparing' || projectStatus === 'processing' || projectStatus === 'prepared') {
      const mode = projectStatus === 'processing' ? 'video' : 'audio';
      setBusy(true);
      pollStatus(sceneStatusUrl, mode);
    } else if (projectStatus === 'ready') {
      fetch(sceneStatusUrl, {cache:'no-store'}).then(response => response.json()).then(result => {
        if (result.audio_url) {
          preparedAudio.src = result.audio_url;
          preparedAudio.hidden = false;
        }
      }).catch(() => {});
    }

    const startProcessing = async mode => {
      setBusy(true);
      progress.hidden = false;
      progress.value = 0;
      status.className = 'job-status';
      status.textContent = mode === 'audio' ? 'Démarrage de la préparation audio…' : 'Démarrage de la génération vidéo…';
      prepareButton.textContent = mode === 'audio' ? 'Préparation en cours…' : 'Préparer la narration';
      if (mode === 'audio') preparedAudio.hidden = true;
      let notificationPermission = null;
      if (mode === 'video' && 'Notification' in window && Notification.permission === 'default') {
        try { notificationPermission = Notification.requestPermission(); } catch {}
      } else if (mode === 'video' && 'Notification' in window) {
        notificationPermission = Promise.resolve(Notification.permission);
      }
      try {
        await saveCurrentScene();
        const action = mode === 'audio'
          ? `/projects/${document.body.dataset.projectId}/prepare-audio/`
          : generateForm.action;
        const response = await fetch(action, {method:'POST', body:new FormData(generateForm)});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Le traitement n’a pas pu démarrer.');
        pollStatus(sceneStatusUrl, mode, notificationPermission);
      } catch(error) {
        status.className = 'job-status error';
        status.textContent = error.message;
        setBusy(false);
        prepareButton.textContent = 'Préparer la narration';
      }
    };

    prepareButton.addEventListener('click', () => startProcessing('audio'));
    generateForm.addEventListener('submit', event => {
      event.preventDefault();
      startProcessing('video');
    });

    document.querySelector('#narrationText')?.addEventListener('input', () => {
      preparedAudio.hidden = true;
    });
    generateForm.querySelectorAll('input[name="voice_id"]').forEach(input => {
      input.addEventListener('change', () => { preparedAudio.hidden = true; });
    });
  }
})();
