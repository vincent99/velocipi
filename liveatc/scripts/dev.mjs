#!/usr/bin/env node
// Dev launcher: runs the liveatc API (air, hot-reload) and the Vite UI together.
//
// Any arguments after `yarn dev` are forwarded to the Go server (intercom-stt),
// so you can point it at a test source instead of ALSA hardware, e.g.:
//   yarn dev --stream https://example.liveatc.net/feed.mp3
//   yarn dev --file testdata/clip.wav
//   yarn dev --config /path/to/velocipi
//
// We use concurrently's programmatic API (not the CLI) so each command string is
// run intact in its own shell -- passing the args as a wrapper-shell argv list
// mangles them (concurrently would treat `--stream`, the URL, etc. as separate
// commands).
import { concurrently } from 'concurrently';

const serverArgs = process.argv.slice(2);
// Quote each arg so values with shell metacharacters survive concurrently's shell.
const quoted = serverArgs.map((a) => JSON.stringify(a)).join(' ');
const goCmd = quoted ? `air -- ${quoted}` : 'air';

const { result } = concurrently(
  [
    { command: goCmd, name: 'go', prefixColor: 'yellow' },
    { command: 'yarn dev:ui', name: 'ui', prefixColor: 'cyan' },
  ],
  { killOthersOn: ['failure', 'success'] }
);

result.then(
  () => process.exit(0),
  () => process.exit(1)
);
