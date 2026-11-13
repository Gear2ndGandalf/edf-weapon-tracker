// ============================================================================
// savefile.js – reads which weapons a player owns out of the game's own save
// file (PC, Steam), so they do not have to be ticked by hand. Used by the
// "Import from game save" panel on HQ (js/hq.js), which loads this file only
// when the panel is opened.
//
// The save is read on the device; nothing is sent anywhere. Only MAIN.GST is
// ever read (it holds armor and weapons; the player's name is in another file).
//
// How a save is laid out (each game checked against real saves; first described
// by the public-domain EDFSaveEditor by FevGrave, https://github.com/FevGrave/EDFSaveEditor):
//   • The whole file is AES in counter mode, with a key that is the same for
//     every player.
//       EDF 5 and 6: AES-256. The key is MD5 of the text  <game> + "MAIN.GST" + ".sav"
//       (as UTF-16LE, <game> being "edf5" or "edf6") followed by the 16 characters
//       Edf5.*_Steam_Ver ; the starting counter is MD5 of  <game> + "MAIN.GST" + ".stm" .
//       tools/test_app.py works both out again from this recipe and compares.
//       EDF 4.1: AES-128 with one fixed key and counter.
//   • Decoded, it starts with "MDB0", a format number, the length of the body,
//     and a checksum of the body, which starts at `body`: CRC-32C, inverted
//     (EDF 5 and 6), or plain CRC-32 (EDF 4.1).
//   • The weapon table is the last part of the file: `rows` entries of `rowSize`
//     bytes. The first four bytes of an entry are a number whose lowest bit says
//     "owned" (other bits mark things like "new"). In EDF 5 and 6 eight more
//     bytes hold the levels of the weapon's upgrades (see starsOf below for how
//     a level becomes the stars the game shows). Which byte belongs to which
//     upgrade differs from weapon to weapon; the game's own weapon files say
//     so, and tools/build_data.py copies that into the "stars" list of
//     data/<game>-save.json.
//   • An entry's position is the weapon's place in the game's own weapon table.
//     data/<game>-save.json lists the tracker's weapon id for each position ("rows")
//     and, for EDF 5 and 6, where each of the weapon's upgrades keeps its star level
//     among the entry's eight star bytes ("stars", see starsOf below).
// ============================================================================

const hex = (s) => new Uint8Array(s.match(/../g).map((b) => parseInt(b, 16)));
// An error whose message is written for the player. HQ shows only these as they are.
const fail = (message) => Object.assign(new Error(message), { readable: true });

// One entry per game whose save can be read. `where` is shown to the player.
// `sum` is the checksum kind: 'crc32c-inverted' or 'crc32'.
export const SAVES = {
  edf41: {
    file: 'MAIN.GST', size: 16504, format: 1, body: 0x18, sum: 'crc32',
    key: hex('dbd394c9e09c52ce77467d6a9f913c81'),
    counter: hex('f5a9402744ee8c270b2e6d97a9c430ca'),
    table: 0x2078, rowSize: 4, rows: 2048,
    map: 'data/edf41-save.json',
    where: 'Documents\\My Games\\EDF4.1\\SAVE_DATA',
  },
  edf5: {
    file: 'MAIN.GST', size: 56584, format: 3, body: 0x20, sum: 'crc32c-inverted',
    key: hex('a79b6f8664af9ca176e49daf0c2c0d00456466352e2a5f537465616d5f566572'),
    counter: hex('0ffab9057470d6e5bd9e4fec4c2c8256'),
    table: 0x7D08, rowSize: 12, rows: 2048,
    map: 'data/edf5-save.json',
    where: 'Documents\\My Games\\EDF5\\SAVE_DATA',
  },
  edf6: {
    file: 'MAIN.GST', size: 56572, format: 3, body: 0x14, sum: 'crc32c-inverted',
    key: hex('4a86f7ce193f8be5ecd6acabb8978262456466352e2a5f537465616d5f566572'),
    counter: hex('f3e7b9f4b102a60a008445840defbdf9'),
    table: 0x7CFC, rowSize: 12, rows: 2048,
    map: 'data/edf6-save.json',
    where: '%LOCALAPPDATA%\\EarthDefenceForce6\\SAVE_DATA',
  },
};

// The two checksums the saves use: CRC-32C (Castagnoli) and the common CRC-32.
const crcTables = {};
function crc(poly, bytes, from) {
  let table = crcTables[poly];
  if (!table) {
    table = crcTables[poly] = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ poly : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let v = 0xFFFFFFFF;
  for (let i = from || 0; i < bytes.length; i++) v = table[(v ^ bytes[i]) & 0xFF] ^ (v >>> 8);
  return (v ^ 0xFFFFFFFF) >>> 0;
}
export const crc32c = (bytes, from) => crc(0x82F63B78, bytes, from);
export const crc32 = (bytes, from) => crc(0xEDB88320, bytes, from);
const checksum = (fmt, bytes) => (fmt.sum === 'crc32' ? crc32(bytes, fmt.body) : (~crc32c(bytes, fmt.body)) >>> 0);

// The list of tracker ids by position in the save, fetched once per game.
const maps = {};
function loadMap(game) {
  if (!maps[game]) {
    const missing = () => fail('The weapon list for reading saves did not load. Check your connection and try again.');
    maps[game] = fetch(SAVES[game].map, { cache: 'no-cache' }).then((r) => { // always the current list, never a stale copy
      if (!r.ok) throw missing();
      return r.json();
    }).then((m) => {
      if (!m || !Array.isArray(m.rows)) throw missing();
      return { rows: m.rows, stars: Array.isArray(m.stars) ? m.stars : null };
    }, (err) => { throw err && err.readable ? err : missing(); }); // no connection, or something that is not the list
    maps[game].catch(() => { delete maps[game]; }); // allow a retry
  }
  return maps[game];
}

// What to say about a file that cannot be this game's save, going by its size alone.
// True for games whose saves hold star levels (EDF 5 and 6).
export const hasStarLevels = (game) => !!SAVES[game] && SAVES[game].rowSize >= 12;

export function wrongFile(game) {
  const fmt = SAVES[game];
  return fail('That is not the right file: ' + fmt.file + ' for this game is ' + fmt.size.toLocaleString('en-US') + ' bytes. Choose ' + fmt.file + ' from a saveslot folder, and check that the Game above is the right one.');
}

// Star levels of one weapon, in the tracker's own order of upgrades. `where` comes from the map
// file: two characters per upgrade, the first saying which of the entry's eight star bytes holds
// it, the second how many steps that upgrade has (as one base-36 digit).
// The byte is the upgrade's level, from 0 to its number of steps. The game shows it as stars so
// that 5 can always be reached: with 5 steps or more the level is shown as it is, and with fewer
// it is stretched onto 0..5, as level * 5 / steps rounded down (this is in the games' own code).
// With 3 steps the levels 0, 1, 2, 3 are shown as 0, 1, 3 and 5 stars.
// Returns { now: [stars per upgrade, as the game shows them], most: [the most each can show] }.
function starsOf(plain, at, where) {
  const now = [];
  const most = [];
  for (let j = 0; j + 1 < where.length; j += 2) {
    const slot = parseInt(where[j], 10);
    const steps = parseInt(where[j + 1], 36);
    if (!(slot >= 0 && slot < 8) || !(steps >= 1)) return null; // not a description this version understands
    const level = Math.min(steps, plain[at + 4 + slot]);
    now.push(steps >= 5 ? level : Math.floor(level * 5 / steps));
    most.push(Math.max(5, steps));
  }
  return { now, most };
}

// Reads one save. `data` is the file's contents (ArrayBuffer).
// Returns { owned: [tracker id, ...], total: how many weapons the tracker lists for this game,
//           stars: { id: [stars per upgrade, in the tracker's order] } for the owned weapons, or null
//           when the game has no stars or their places in the save are not known,
//           most:  { id: [the most stars each of those upgrades can have] } (null with stars) }.
// Throws an Error with a message for the player when the file is not a save this can read.
export async function readSave(game, data) {
  const fmt = SAVES[game];
  if (!fmt) throw fail('Saves of this game cannot be read yet.');
  const name = fmt.file;
  if (!(data instanceof ArrayBuffer) || data.byteLength !== fmt.size) throw wrongFile(game);
  const subtle = self.crypto && self.crypto.subtle;
  if (!subtle) throw fail('This browser cannot read saves here. Open the tracker over https and try again.');
  let plain;
  try {
    const key = await subtle.importKey('raw', fmt.key, { name: 'AES-CTR' }, false, ['decrypt']);
    plain = new Uint8Array(await subtle.decrypt({ name: 'AES-CTR', counter: fmt.counter, length: 128 }, key, data));
  } catch (e) {
    throw fail('The save could not be decoded in this browser.');
  }
  const view = new DataView(plain.buffer, plain.byteOffset, plain.byteLength);
  const magic = String.fromCharCode(plain[0], plain[1], plain[2], plain[3]);
  if (magic !== 'MDB0') throw fail('That file is not ' + name + ' from this game. Choose ' + name + ' from a saveslot folder, and check that the Game above is the right one.');
  if (view.getUint32(4, true) !== fmt.format || view.getUint32(8, true) !== fmt.size - fmt.body) {
    throw fail('This save is in a format the tracker does not know yet (the game may have been updated). Nothing was changed.');
  }
  if (view.getUint32(12, true) !== checksum(fmt, plain)) {
    throw fail('The save file is damaged (its checksum does not match). Nothing was changed.');
  }
  if (fmt.table + fmt.rows * fmt.rowSize > plain.length) throw fail('The save file is shorter than expected. Nothing was changed.');
  const map = await loadMap(game);
  const ids = map.rows;
  const places = fmt.rowSize >= 12 ? map.stars : null;
  const owned = [];
  const stars = places ? {} : null;
  const most = places ? {} : null;
  for (let i = 0; i < fmt.rows && i < ids.length; i++) {
    const at = fmt.table + i * fmt.rowSize;
    if (typeof ids[i] !== 'string' || !(view.getUint32(at, true) & 1)) continue;
    owned.push(ids[i]);
    if (places && typeof places[i] === 'string' && places[i]) {
      const s = starsOf(plain, at, places[i]);
      if (s) {
        stars[ids[i]] = s.now;
        most[ids[i]] = s.most;
      }
    }
  }
  return { owned, total: ids.filter((id) => typeof id === 'string').length, stars, most };
}
