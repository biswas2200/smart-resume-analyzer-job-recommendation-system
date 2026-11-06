import { register } from '../api/auth-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, hide, setBusy, setFieldError, setText, show } from '../core/dom.js';
import { validateConfirmPassword, validateEmail, validateNewPassword } from '../core/validation.js';
import { offerToContinue } from '../components/signed-in.js';

// Create an account, backed by `POST /auth/register`. A successful registration returns a
// token, so the new user goes straight on to upload a resume.

const form = byId('register-form');
const emailInput = byId('register-email');
const passwordInput = byId('register-password');
const confirmInput = byId('register-confirm-password');
const submitButton = byId('register-submit');
const errorBanner = byId('register-error');

offerToContinue(form);

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const email = emailInput.value.trim();
  const password = passwordInput.value;

  const errors = [
    [emailInput, validateEmail(email)],
    [passwordInput, validateNewPassword(password)],
    [confirmInput, validateConfirmPassword(password, confirmInput.value)],
  ];
  errors.forEach(([input, message]) => setFieldError(input, message));
  if (errors.some(([, message]) => message !== null)) {
    return;
  }

  hide(errorBanner);
  setBusy(submitButton, true, 'Creating account…');

  try {
    await register(email, password);
    location.href = 'upload.html';
  } catch (error) {
    setBusy(submitButton, false);
    setText(errorBanner, extractApiErrorMessage(error, 'Could not create the account. Please try again.'));
    show(errorBanner);
  }
});
