# ModelOS Annotate frontend

The Vite build contains the editorial landing (`index.html` and `landing.html`) and approved React workspace (`next.html`). All are served under `/app1/`.

See [the demo guide](../DEMO.md) for backend/runtime setup, startup commands, workflow, verification and limitations.

```bash
npm ci
npm run lint
npm run build
npm test
VITE_BACKEND_URL=http://127.0.0.1:8011 npm run dev
```

Type checking targets the active landing/workspace and their shared dependencies. The original application remains in source/history and is excluded from the active build.
