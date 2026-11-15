/** All durable reads/writes cross this boundary; the browser has no database key. */
export async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`/api${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail
            .map((item) => `${item.loc.at(-1)}: ${item.msg}`)
            .join("；")
        : data.detail;
      throw new Error(detail || `请求失败（${response.status}）`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请重试。");
    if (error instanceof TypeError)
      throw new Error("无法连接后端，请检查服务是否运行。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
export function write(path, method, data) {
  return api(path, { method, body: JSON.stringify(data) });
}
export const requestId = () => crypto.randomUUID();
