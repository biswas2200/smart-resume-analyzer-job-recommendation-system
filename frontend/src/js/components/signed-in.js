import { byId, hide, setText, show } from '../core/dom.js';
import { clearSession, getUser, isAuthenticated } from '../core/session.js';

/**
 * The sign-in and create-account pages opened by someone already signed in: swaps the form
 * for a panel that offers to go to the dashboard or to switch accounts.
 * Returns true when the panel was shown.
 */
export function offerToContinue(form) {
  if (!isAuthenticated()) {
    return false;
  }
  hide(form);
  setText(byId('signed-in-email'), getUser().email);
  byId('switch-account').addEventListener('click', () => {
    clearSession();
    location.reload();
  });
  show(byId('signed-in'));
  return true;
}
