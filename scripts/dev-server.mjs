import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer, request as proxyHttpRequest } from "node:http";
import { extname, join, normalize } from "node:path";

const host = "127.0.0.1";
const port = Number(process.env.PORT || 4173);
const root = process.cwd();
const apiOrigin = new URL(process.env.API_ORIGIN || "http://127.0.0.1:8000");
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".mp4": "video/mp4",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function proxyRequest(request, response) {
  const proxy = proxyHttpRequest({
    hostname: apiOrigin.hostname,
    port: apiOrigin.port,
    path: request.url,
    method: request.method,
    headers: { ...request.headers, host: apiOrigin.host },
  }, (upstream) => {
    response.writeHead(upstream.statusCode || 502, upstream.headers);
    upstream.pipe(response);
  });
  proxy.on("error", () => {
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ detail: "Локальный FastAPI недоступен" }));
  });
  request.pipe(proxy);
}

createServer((request, response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, `http://${host}`).pathname); }
  catch { response.writeHead(400);response.end("Bad request");return; }
  if (pathname.startsWith("/api/") || pathname.startsWith("/media/")) {
    proxyRequest(request, response);
    return;
  }
  const requested = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
  const iconPath = "icons/regular/";
  // Serve browser assets only, never secrets, repository files or backend sources.
  const asset = /^(?:index\.html|styles\.css|app\.js|ui\/[a-z-]+\.(?:css|js)|ui\/landing-assets\/[a-z0-9-]+\.(?:jpg|png)|assets\/[a-z-]+\.(?:png|webp|mp4|svg)|icons\/regular\/[a-zA-Z0-9.-]+\.(?:css|woff2?|ttf))$/.test(requested);
  const route = /^(?:today|login|account|library|competitors|content-plan|remixes\/[a-zA-Z0-9_-]+)$/.test(requested);
  if (!asset && !route) { response.writeHead(404);response.end("Not found");return; }
  const mapped = requested.startsWith(iconPath)
    ? join("node_modules", "@phosphor-icons", "web", "src", "regular", requested.slice(iconPath.length))
    : requested;
  let file = normalize(join(root, mapped));

  if (!file.startsWith(root)) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  if (!existsSync(file) || !statSync(file).isFile()) {
    if (extname(mapped)) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("Not found");
      return;
    }
    file = join(root, "index.html");
  }

  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": types[extname(file)] || "application/octet-stream",
  });
  createReadStream(file).pipe(response);
}).listen(port, host, () => {
  console.log(`Local: http://${host}:${port}`);
});
