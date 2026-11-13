// The one place the app version lives. Loaded by every page and by sw.js.
// Format: vMAJOR.MINOR.PATCH
//   MAJOR – the save format changes in a way older exports cannot follow
//   MINOR – new features
//   PATCH – fixes and data corrections
// Changing this number is also what makes phones fetch the new files,
// so bump it with every published change and add a line to CHANGELOG.md.
self.APP_VERSION = '1.9.0';

// Shown once on HQ after a phone updates to this version. Keep it to a few short items.
self.APP_NEWS = [
  'Upgrades now follow the equipment screen of EDF 5 and 6 line by line',
  'A line the game shows with one star for two values (Damage and Count) shows that star too',
  'Stars imported with v1.8 can be slightly off: import your save again and choose Match the save (or Raise stars)',
];
