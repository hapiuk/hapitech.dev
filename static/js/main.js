// static/js/main.js

async function readJsonSafe(res){
  const ct = (res.headers.get("content-type") || "").toLowerCase();

  // If server returns HTML (redirect/login page/error), don't try to parse JSON.
  if(!ct.includes("application/json")){
    return {__not_json:true, text: await res.text()};
  }

  try{
    return await res.json();
  }catch(e){
    return {__not_json:true, text: await res.text()};
  }
}

// login
const loginForm = document.getElementById('loginForm');
const loginBtn = document.getElementById('loginBtn');
const loginMsg = document.getElementById('loginMsg');

if(loginBtn){
  loginBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    loginMsg.textContent = "";

    const username = (document.getElementById('username')?.value || "").trim();
    const password = document.getElementById('password')?.value || "";

    if(!username || !password){
      loginMsg.style.color = "#ffb7b7";
      loginMsg.textContent = "Please fill both fields.";
      return;
    }

    loginBtn.disabled = true;
    loginBtn.textContent = "Signing in...";

    try{
      const res = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'same-origin'
      });

      const data = await readJsonSafe(res);

      // If we got HTML instead of JSON, it usually means a redirect or an error page.
      if(data && data.__not_json){
        if(res.ok){
          loginMsg.style.color = "#bfffdc";
          loginMsg.textContent = "Login successful — redirecting...";
          setTimeout(() => { window.location.href = "/"; }, 250);
          return;
        }
        loginMsg.style.color = "#ffb7b7";
        loginMsg.textContent = "Login failed.";
        return;
      }

      if(res.ok && data.success){
        loginMsg.style.color = "#bfffdc";
        loginMsg.textContent = "Login successful — redirecting...";

        // Let the server decide where to send the user based on role.
        setTimeout(() => { window.location.href = "/"; }, 250);
        return;
      }

      loginMsg.style.color = "#ffb7b7";
      loginMsg.textContent = (data && data.message) ? data.message : "Login failed";
    }catch(err){
      loginMsg.style.color = "#ffb7b7";
      loginMsg.textContent = "Network error";
      console.error(err);
    }finally{
      loginBtn.disabled = false;
      loginBtn.textContent = "Sign In";
    }
  });
}

// OTP Email Login
const toggleOtpBtn = document.getElementById('toggleOtpBtn');
const togglePwBtn = document.getElementById('togglePwBtn');
const otpForm = document.getElementById('otpForm');
const requestOtpBtn = document.getElementById('requestOtpBtn');
const verifyOtpBtn = document.getElementById('verifyOtpBtn');
const otpMsg = document.getElementById('otpMsg');
const otpStep1 = document.getElementById('otpStep1');
const otpStep2 = document.getElementById('otpStep2');

if(toggleOtpBtn && otpForm && loginForm){
  toggleOtpBtn.addEventListener('click', () => {
    loginForm.style.display = 'none';
    otpForm.style.display = 'grid';
  });
}

if(togglePwBtn && otpForm && loginForm){
  togglePwBtn.addEventListener('click', () => {
    otpForm.style.display = 'none';
    loginForm.style.display = 'grid';
  });
}

if(requestOtpBtn){
  requestOtpBtn.addEventListener('click', async () => {
    const email = (document.getElementById('otpEmail')?.value || "").trim();
    if(!email){
      if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = "Please enter your email."; }
      return;
    }
    requestOtpBtn.disabled = true;
    requestOtpBtn.textContent = "Sending code...";

    try {
      const res = await fetch('/login-code/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await readJsonSafe(res);
      if(res.ok && data.success){
        if(otpMsg){ otpMsg.style.color = "#bfffdc"; otpMsg.textContent = data.message; }
        if(otpStep1) otpStep1.style.display = 'none';
        if(otpStep2) otpStep2.style.display = 'block';
      } else {
        if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = data.message || "Failed to send code."; }
      }
    } catch(err) {
      if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = "Network error."; }
    } finally {
      requestOtpBtn.disabled = false;
      requestOtpBtn.textContent = "Send Login Code";
    }
  });
}

if(verifyOtpBtn){
  verifyOtpBtn.addEventListener('click', async () => {
    const code = (document.getElementById('otpCode')?.value || "").trim();
    if(!code || code.length < 6){
      if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = "Enter 6-digit verification code."; }
      return;
    }
    verifyOtpBtn.disabled = true;
    verifyOtpBtn.textContent = "Verifying...";

    try {
      const res = await fetch('/login-code/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await readJsonSafe(res);
      if(res.ok && data.success){
        if(otpMsg){ otpMsg.style.color = "#bfffdc"; otpMsg.textContent = "Code verified — logging in..."; }
        setTimeout(() => { window.location.href = "/"; }, 250);
      } else {
        if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = data.message || "Verification failed."; }
      }
    } catch(err) {
      if(otpMsg){ otpMsg.style.color = "#ffb7b7"; otpMsg.textContent = "Network error."; }
    } finally {
      verifyOtpBtn.disabled = false;
      verifyOtpBtn.textContent = "Verify Code & Sign In";
    }
  });
}

// contact popup behaviour
const contactBubble = document.getElementById('contactBubble');
const contactPopup = document.getElementById('contactPopup');
const contactClose = document.getElementById('contactClose');
const contactForm = document.getElementById('contactForm');
const sendContact = document.getElementById('sendContact');
const contactStatus = document.getElementById('contactStatus');

function showContact(){
  if(contactPopup) contactPopup.style.display = 'block';
}
function hideContact(){
  if(contactPopup) contactPopup.style.display = 'none';
}

if(contactBubble){
  contactBubble.addEventListener('click', () => {
    if(!contactPopup) return;
    if(contactPopup.style.display === 'block') hideContact();
    else showContact();
  });
}

if(contactClose){
  contactClose.addEventListener('click', hideContact);
}

// also open when clicking help link
const helpLink = document.getElementById('helpLink');
if(helpLink){
  helpLink.addEventListener('click', (e) => {
    e.preventDefault();
    showContact();
  });
}

// send contact
if(sendContact){
  sendContact.addEventListener('click', async (e) => {
    e.preventDefault();
    if(contactStatus) contactStatus.textContent = "";

    const name = (document.getElementById('contactName')?.value || "").trim();
    const email = (document.getElementById('contactEmail')?.value || "").trim();
    const message = (document.getElementById('contactMessage')?.value || "").trim();

    if(!name || !email || !message){
      if(contactStatus){
        contactStatus.style.color = "#ffb7b7";
        contactStatus.textContent = "Please fill all fields.";
      }
      return;
    }

    sendContact.disabled = true;
    sendContact.textContent = "Sending...";

    try{
      const res = await fetch('/contact', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name, email, message }),
        credentials: 'same-origin'
      });

      const data = await readJsonSafe(res);

      if(data && data.__not_json){
        if(res.ok){
          if(contactStatus){
            contactStatus.style.color = "#bfffdc";
            contactStatus.textContent = "Sent — thanks!";
          }
          setTimeout(() => { hideContact(); if(contactStatus) contactStatus.textContent = ""; }, 1000);
          if(contactForm) contactForm.reset();
          return;
        }
        if(contactStatus){
          contactStatus.style.color = "#ffb7b7";
          contactStatus.textContent = "Failed to send";
        }
        return;
      }

      if(res.ok && data.success){
        if(contactStatus){
          contactStatus.style.color = "#bfffdc";
          contactStatus.textContent = data.message || "Sent — thanks!";
        }
        setTimeout(() => { hideContact(); if(contactStatus) contactStatus.textContent = ""; }, 1000);
        if(contactForm) contactForm.reset();
        return;
      }

      if(contactStatus){
        contactStatus.style.color = "#ffb7b7";
        contactStatus.textContent = (data && data.message) ? data.message : "Failed to send";
      }
    }catch(err){
      if(contactStatus){
        contactStatus.style.color = "#ffb7b7";
        contactStatus.textContent = "Network error sending message";
      }
      console.error(err);
    }finally{
      sendContact.disabled = false;
      sendContact.textContent = "Send";
    }
  });
}
