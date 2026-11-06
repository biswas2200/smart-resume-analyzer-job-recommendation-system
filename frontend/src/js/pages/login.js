import { login } from '../api/auth-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, hide, setBusy, setFieldError, setText, show } from '../core/dom.js';
import { validateEmail, validateLoginPassword } from '../core/validation.js';
import { offerToContinue } from '../components/signed-in.js';

// Sign in to an existing account, backed by `POST /auth/login`.

const form = byId('login-form');
const emailInput = byId('login-email');
const passwordInput = byId('login-password');
const submitButton = byId('login-submit');
const errorBanner = byId('login-error');

offerToContinue(form);

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const email = emailInput.value.trim();
  const password = passwordInput.value;

  const emailError = validateEmail(email);
  const passwordError = validateLoginPassword(password);
  setFieldError(emailInput, emailError);
  setFieldError(passwordInput, passwordError);
  if (emailError || passwordError) {
    return;
  }

  hide(errorBanner);
  setBusy(submitButton, true, 'Signing in…');

  try {
    await login(email, password);
    location.href = 'dashboard.html';
  } catch (error) {
    setBusy(submitButton, false);
    setText(errorBanner, extractApiErrorMessage(error, 'Could not sign in. Please try again.'));
    show(errorBanner);
  }
});
