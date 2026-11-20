import { apiGet, apiPost, getToken, setSession } from './api.js';

if (getToken()) {
  window.location.replace('dashboard.html');
}

const alertBox = document.getElementById('authAlert');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const captchaImg = document.getElementById('captchaImg');
const captchaInput = document.getElementById('loginCaptcha');
let captchaToken = null;

function showAlert(message, type) {
  alertBox.textContent = message;
  alertBox.className = 'alert alert-' + (type || 'error');
}

function clearAlert() {
  alertBox.className = 'alert hidden';
  alertBox.textContent = '';
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  if (label) button.textContent = label;
}

async function loadCaptcha() {
  captchaInput.value = '';
  captchaImg.removeAttribute('src');
  try {
    const data = await apiGet('/auth/captcha', null, { public: true });
    captchaToken = data.captcha_token;
    captchaImg.src = data.imagen;
  } catch (e) {
    captchaToken = null;
    showAlert(e.message);
  }
}

function selectTab(name) {
  const login = name === 'login';
  document.getElementById('tabLogin').classList.toggle('active', login);
  document.getElementById('tabRegister').classList.toggle('active', !login);
  loginForm.classList.toggle('hidden', !login);
  registerForm.classList.toggle('hidden', login);
  clearAlert();
  if (login) loadCaptcha();
}

document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
  tab.addEventListener('click', () => selectTab(tab.dataset.tab));
});

document.getElementById('captchaReload').addEventListener('click', loadCaptcha);

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearAlert();
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const respuesta = captchaInput.value.trim();
  if (!username || !password) {
    showAlert('Ingrese usuario y contraseña');
    return;
  }
  if (!captchaToken || !respuesta) {
    showAlert('Resuelva el CAPTCHA para continuar');
    return;
  }
  const button = document.getElementById('loginSubmit');
  setBusy(button, true, 'Ingresando...');
  try {
    const data = await apiPost(
      '/auth/login',
      { username, password, captcha_token: captchaToken, captcha_respuesta: respuesta },
      { public: true }
    );
    setSession(data.token, data.usuario);
    window.location.replace('dashboard.html');
  } catch (e) {
    showAlert(e.message);
    setBusy(button, false, 'Ingresar');
    loadCaptcha();
  }
});

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearAlert();
  const username = document.getElementById('regUsername').value.trim();
  const password = document.getElementById('regPassword').value;
  const confirm = document.getElementById('regPassword2').value;
  if (!/^[A-Za-z0-9_.-]{3,50}$/.test(username)) {
    showAlert('El usuario debe tener entre 3 y 50 caracteres (letras, números, . _ -)');
    return;
  }
  if (password.length < 8) {
    showAlert('La contraseña debe tener al menos 8 caracteres');
    return;
  }
  if (password !== confirm) {
    showAlert('Las contraseñas no coinciden');
    return;
  }
  const button = document.getElementById('registerSubmit');
  setBusy(button, true, 'Creando...');
  try {
    const data = await apiPost('/auth/register', { username, password }, { public: true });
    registerForm.reset();
    selectTab('login');
    document.getElementById('loginUsername').value = data.username;
    showAlert('Cuenta creada. Ya puede iniciar sesión.', 'success');
  } catch (e) {
    showAlert(e.message);
  } finally {
    setBusy(button, false, 'Crear cuenta');
  }
});

loadCaptcha();
