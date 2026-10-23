import { post } from '../api.js';
import { h, clear, field } from '../ui.js';

export function renderLogin(root, onLoggedIn) {
  const user = h('input', { class: 'input', id: 'login-user', type: 'email', autocomplete: 'username', required: true, value: '' });
  const pass = h('input', { class: 'input', id: 'login-pass', type: 'password', autocomplete: 'current-password', required: true });
  const err = h('div', { class: 'error-text', role: 'alert' });
  const submit = h('button', { class: 'btn primary', type: 'submit', text: 'Log in' });
  const form = h('form', {
    class: 'card card-body stack',
    onsubmit: async e => {
      e.preventDefault();
      err.textContent = '';
      submit.disabled = true;
      try {
        onLoggedIn(await post('auth/login', { username: user.value, password: pass.value }));
      } catch (ex) {
        err.textContent = ex.message;
        pass.select();
      } finally {
        submit.disabled = false;
      }
    },
  },
  h('h1', { text: 'Sign in' }),
  field('Email', user),
  field('Password', pass),
  err,
  submit);
  clear(root, h('div', { class: 'login-wrap' },
    h('div', { class: 'login' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark', text: 'G' }), 'Gateway Manager'),
      form)));
  user.focus();
}
