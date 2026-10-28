import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const commit = "469a55dc84ea7a9e077161a8b454871a9adaff35";
const base = `https://oceanbase-seekdb-builds.s3.ap-southeast-1.amazonaws.com/js-bindings/all_commits/${commit}`;
const platform = `${process.platform}-${process.arch === "arm64" ? "arm64" : "x64"}`;
const dest = path.join(root, "vendor", "bindings", commit, platform);
const zipPath = path.join(dest, `seekdb-js-bindings-${platform}.zip`);
const nodePath = path.join(dest, "seekdb.node");

if (fs.existsSync(nodePath)) {
  console.log(`已有 ${nodePath}`);
  process.exit(0);
}

fs.mkdirSync(dest, { recursive: true });
const url = `${base}/seekdb-js-bindings-${platform}.zip`;
const curl = spawnSync(
  "curl",
  ["-fL", "--retry", "3", "-o", zipPath, url],
  { stdio: "inherit" }
);
if (curl.status !== 0) process.exit(curl.status || 1);
const unzip = spawnSync("unzip", ["-o", zipPath, "-d", dest], { stdio: "inherit" });
if (unzip.status !== 0) process.exit(unzip.status || 1);
if (!fs.existsSync(nodePath)) {
  console.error(`压缩包里没有 seekdb.node：${zipPath}`);
  process.exit(1);
}
console.log(`绑定已放到 ${dest}`);
