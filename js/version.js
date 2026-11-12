// The one place the app version lives. Loaded by every page and by sw.js.
// Format: vMAJOR.MINOR.PATCH
//   MAJOR – the save format changes in a way older exports cannot follow
//   MINOR – new features
//   PATCH – fixes and data corrections
// Changing this number is also what makes phones fetch the new files,
// so bump it with every published change and add a line to CHANGELOG.md.
self.APP_VERSION = '1.3.1';

// Shown once on HQ after a phone updates to this version. Keep it to a few short items.
self.APP_NEWS = [
  'Tap a star to set that level',
  'Where each weapon drops',
  'Two profiles',
  'Last export date on HQ',
];
