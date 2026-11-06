import { byId, hide, show } from '../core/dom.js';
import { isAuthenticated } from '../core/session.js';
import { hydrateIcons } from '../components/icons.js';

// The public landing page: draws its icons, for a signed-in visitor swaps the sign-in
// buttons for a link straight to the dashboard.

hydrateIcons();
if (isAuthenticated()) {
  hide(byId('signed-out-actions'));
  show(byId('signed-in-action'));
}
