// Interface language (English / Spanish).
//
// The app is written in English. When the language is Spanish, this module
// translates the page in place: it walks the text of the document (and the
// title / placeholder / aria-label attributes), looks every piece of text up
// in the dictionary of i18n-es.js and keeps doing so for whatever the page
// renders later (a MutationObserver). Text that is not in the dictionary
// (player names, moves, opening names) is left as it is.
//
// The coach's review messages are different: they are written in Spanish on
// the server (analysis/coach_es.py), because their grammar depends on who moved.
import { EXACT, PATTERNS } from './i18n-es.js';

export const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
const ATTRIBUTES = ['title', 'placeholder', 'aria-label'];
const SKIP = new Set(['SCRIPT', 'STYLE', 'CODE', 'CG-CONTAINER', 'CANVAS']);

/** Spanish for an English UI string, or null when it is not in the dictionary. */
function lookup(text) {
  const key = text.replace(/\s+/g, ' ').trim();
  if (key.length < 2) return null;
  if (Object.prototype.hasOwnProperty.call(EXACT, key)) return EXACT[key];
  for (const [pattern, replacement] of PATTERNS) {
    const match = key.match(pattern);
    if (match) return typeof replacement === 'function' ? replacement(match) : key.replace(pattern, replacement);
  }
  return null;
}

/** Translate a string (returns it unchanged in English or when unknown). */
export function t(text) {
  if (lang !== 'es' || !text) return text;
  const found = lookup(text);
  if (found === null) return text;
  // keep the spaces around the text: they separate it from its neighbours
  return text.match(/^\s*/)[0] + found + text.match(/\s*$/)[0];
}

function translateNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    const next = t(node.nodeValue);
    if (next !== node.nodeValue) node.nodeValue = next;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE || SKIP.has(node.tagName)) return;
  for (const name of ATTRIBUTES) {
    const value = node.getAttribute(name);
    if (value) { const next = t(value); if (next !== value) node.setAttribute(name, next); }
  }
  for (const child of node.childNodes) translateNode(child);
}

if (lang === 'es') {
  translateNode(document.body);
  document.title = t(document.title);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'childList') for (const node of record.addedNodes) translateNode(node);
      else translateNode(record.target);       // changed text or attribute
    }
  }).observe(document.body, {
    childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTES,
  });
  new MutationObserver(() => {
    const next = t(document.title);
    if (next !== document.title) document.title = next;
  }).observe(document.querySelector('title'), { childList: true });
}
document.documentElement.classList.add('i18n-ready');     // base.html hides the page until now
