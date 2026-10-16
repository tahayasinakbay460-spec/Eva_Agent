import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-config-next'in varsayılan "kontrol etme" listesini burada yeniden tanımlıyoruz.
  globalIgnores([
    // eslint-config-next'in varsayılan olarak atladığı klasör/dosyalar:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
