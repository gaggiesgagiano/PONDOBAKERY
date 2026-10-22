/* Photo boxes (staff and drivers): pick a photo from the computer (big phone photos are made smaller first),
   or take one with the laptop camera. Works for every <div class="photo-widget"> on the page.
   data-shape="portrait" (people, 3:4) or "landscape" (cars, 4:3). */
(function(){
  function setup(w){
    var form = w.querySelector('form'); if (!form) return;
    var input = form.querySelector('input[type=file]'), box = w.querySelector('.sphoto'), msg = w.querySelector('.photo-msg');
    var pick = form.querySelector('.pick'), start = form.querySelector('.cam-start'), snap = form.querySelector('.cam-snap'),
        stop = form.querySelector('.cam-stop'), rem = form.querySelector('.remove'), busyEl = w.querySelector('.photo-busy');
    var land = w.dataset.shape === 'landscape', TW = land ? 800 : 600, TH = land ? 600 : 800;
    var stream = null, video = null, keep = box.innerHTML, first = msg ? msg.innerHTML : '';
    function say(t){ if (msg) msg.textContent = t; }
    function busy(){ if (busyEl) busyEl.hidden = false; }
    function send(blob, name){
      if (blob && window.DataTransfer) { var dt = new DataTransfer(); dt.items.add(new File([blob], name, {type: 'image/jpeg'})); input.files = dt.files; }
      busy(); form.submit();
    }
    input.addEventListener('change', function(){
      var f = input.files[0]; if (!f) return;
      if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 500000 || !window.createImageBitmap || !window.DataTransfer) { busy(); form.submit(); return; }
      createImageBitmap(f).then(function(bmp){
        var sc = Math.min(1, 1000 / Math.max(bmp.width, bmp.height)), c = document.createElement('canvas');
        c.width = Math.round(bmp.width * sc); c.height = Math.round(bmp.height * sc);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(function(b){ send(b, 'photo.jpg'); }, 'image/jpeg', 0.88);
      }).catch(function(){ busy(); form.submit(); });
    });
    function camMode(on){ start.hidden = on; pick.hidden = on; if (rem) rem.hidden = on; snap.hidden = !on; stop.hidden = !on; }
    function camOff(){ if (stream) { stream.getTracks().forEach(function(t){ t.stop(); }); stream = null; } box.innerHTML = keep; camMode(false); }
    if (start) start.addEventListener('click', function(){
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { say('This computer has no camera the program can use. Use “Add photo” instead.'); return; }
      say('Starting the camera …');
      navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 960}, facingMode: land ? 'environment' : 'user'}, audio: false}).then(function(s){
        stream = s; video = document.createElement('video'); video.playsInline = true; video.muted = true; video.srcObject = s;
        if (land) video.style.transform = 'none';
        box.innerHTML = ''; box.appendChild(video);
        if (!land) { var g = document.createElement('div'); g.className = 'guide'; box.appendChild(g); }
        video.play(); camMode(true);
        say(land ? 'Show the whole car with the number plate, then click Snap.' : 'Face inside the oval, look at the camera, then click Snap.');
      }).catch(function(err){
        say((err && err.name === 'NotAllowedError') ? 'The camera is blocked. Allow it (camera sign at the top of the window) and try again – or use “Add photo”.'
                                                     : 'No camera found on this computer. Use “Add photo” with a photo from a phone.');
      });
    });
    if (stop) stop.addEventListener('click', function(){ camOff(); if (msg) msg.innerHTML = first; });
    if (snap) snap.addEventListener('click', function(){
      var vw = video.videoWidth, vh = video.videoHeight; if (!vw) return;
      var tw = vw, th = vh; if (vw / vh > TW / TH) tw = Math.round(vh * TW / TH); else th = Math.round(vw * TH / TW);
      var c = document.createElement('canvas'); c.width = TW; c.height = TH;
      c.getContext('2d').drawImage(video, (vw - tw) / 2, (vh - th) / 2, tw, th, 0, 0, TW, TH);
      snap.disabled = true;
      c.toBlob(function(b){ if (stream) stream.getTracks().forEach(function(t){ t.stop(); }); send(b, 'camera.jpg'); }, 'image/jpeg', 0.9);
    });
    window.addEventListener('pagehide', function(){ if (stream) stream.getTracks().forEach(function(t){ t.stop(); }); });
  }
  document.querySelectorAll('.photo-widget').forEach(setup);
})();
