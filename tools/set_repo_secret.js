/**
 * Utility to encrypt and upload repository secrets to GitHub Actions
 * using libsodium sealed box encryption and the repository public key.
 */
import https from "https";
import sodium from "libsodium-wrappers";

const REPO = "vjumbo264/sentinel-fx";

export function githubRequest(method, path, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = https.request({
      hostname: "api.github.com",
      path,
      method,
      headers: {
        "Authorization": `Bearer ${token}`,
        "User-Agent": "sentinel-secrets-tool",
        "Accept": "application/vnd.github.v3+json",
        ...(data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {})
      }
    }, res => {
      let resData = "";
      res.on("data", c => resData += c);
      res.on("end", () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(resData ? JSON.parse(resData) : { ok: true }); }
          catch(_) { resolve({ ok: true, text: resData }); }
        } else {
          reject(new Error(`GitHub API error ${res.statusCode}: ${resData}`));
        }
      });
    });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}

export async function setRepoSecret(secretName, secretValue, token) {
  await sodium.ready;
  // 1. Fetch public key
  const pk = await githubRequest("GET", `/repos/${REPO}/actions/secrets/public-key`, token);
  
  // 2. Encrypt value with crypto_box_seal
  const bkey = Buffer.from(pk.key, "base64");
  const bsec = Buffer.from(secretValue);
  const enc = sodium.crypto_box_seal(bsec, bkey);
  const encrypted_value = Buffer.from(enc).toString("base64");

  // 3. Upload secret
  await githubRequest("PUT", `/repos/${REPO}/actions/secrets/${secretName}`, token, {
    encrypted_value,
    key_id: pk.key_id
  });
  return { ok: true, secret: secretName, key_id: pk.key_id };
}

if (process.argv[1] && process.argv[1].endsWith("set_repo_secret.js")) {
  const [,, name, val] = process.argv;
  const token = process.env.GITHUB_PAT || process.env.GH_CHAIN_PAT;
  if (!name || !val || !token) {
    console.error("Usage: GITHUB_PAT=... node tools/set_repo_secret.js <SECRET_NAME> <SECRET_VALUE>");
    process.exit(1);
  }
  setRepoSecret(name, val, token)
    .then(r => console.log(`Secret ${name} updated successfully`))
    .catch(err => { console.error("Error setting secret:", err.message); process.exit(1); });
}
