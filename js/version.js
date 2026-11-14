// The one place the app version lives. Loaded by every page and by sw.js.
// Format: vMAJOR.MINOR.PATCH
//   MAJOR – the save format changes in a way older exports cannot follow
//   MINOR – new features
//   PATCH – fixes and data corrections
// Changing this number is also what makes phones fetch the new files,
// so bump it with every published change and add a line to CHANGELOG.md.
self.APP_VERSION = '1.9.1';

// Shown once on HQ after a phone updates to this version. Keep it to a few short items.
self.APP_NEWS = [
  'Italic text is no longer cut off at the right edge',
  'The list of upgrades stays where you scrolled it while you change stars',
  'Under the Missing and To upgrade filters a change no longer lands on the wrong weapon',
  'If you imported stars with v1.8, import the save again and choose Match the save when it is offered (otherwise Add or Raise stars)',
];
