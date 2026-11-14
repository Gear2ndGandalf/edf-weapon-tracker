// The one place the app version lives. Loaded by every page and by sw.js.
// Format: vMAJOR.MINOR.PATCH
//   MAJOR – the save format changes in a way older exports cannot follow
//   MINOR – new features
//   PATCH – fixes and data corrections
// Changing this number is also what makes phones fetch the new files,
// so bump it with every published change and add a line to CHANGELOG.md.
self.APP_VERSION = '1.10.0';

// Shown once on HQ after a phone updates to this version. Keep it to a few short items.
self.APP_NEWS = [
  'Upgrades with fewer than five steps now move only through the stars the game can show, such as 0, 1, 3 and 5',
  'Each upgrade also shows its stars the way the game writes them, for example ☆4 or ★5',
  'Fully upgraded is now counted out of the weapons that have upgrades, so you can tell when you are done',
  'The Empty and Not Equipped placeholders are no longer counted as weapons, so EDF 5 and EDF 6 each list four fewer',
];
