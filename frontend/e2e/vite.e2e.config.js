// Vite config for the browser tests: the real app, with Firebase swapped for
// e2e/firebase-stub.js and the API pointed at the test backend (port 8010).
import { fileURLToPath } from "node:url";
import { defineConfig, mergeConfig } from "vite";
import base from "../vite.config.js";

const stub = fileURLToPath(new URL("./firebase-stub.js", import.meta.url));

export default mergeConfig(
  base,
  defineConfig({
    resolve: {
      alias: [
        { find: /^firebase\/auth$/, replacement: stub },
        { find: /^.*\/firebase\/firebase(\.js)?$/, replacement: stub },
      ],
    },
    define: {
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify("http://127.0.0.1:8010"),
    },
    server: { port: 5198, strictPort: true },
  }),
);
