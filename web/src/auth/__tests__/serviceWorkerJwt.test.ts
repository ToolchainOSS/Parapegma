import { describe, it, expect } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const SW_PATH = resolve(process.cwd(), "public/sw.js");

function toBase64Url(bytes: Uint8Array): string {
  return Buffer.from(bytes)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createIndexedDbMock(values: Record<string, unknown>): IDBFactory {
  return {
    open: () => {
      const request: Partial<IDBOpenDBRequest> = {};
      queueMicrotask(() => {
        const db: Partial<IDBDatabase> = {
          transaction: () => {
            const tx: Partial<IDBTransaction> = {
              objectStore: () => {
                const store: Partial<IDBObjectStore> = {
                  get: (key: IDBValidKey) => {
                    const req: Partial<IDBRequest> = {};
                    queueMicrotask(() => {
                      req.result = values[String(key)] ?? null;
                      req.onsuccess?.(new Event("success"));
                    });
                    return req as IDBRequest;
                  },
                };
                return store as IDBObjectStore;
              },
            };
            return tx as IDBTransaction;
          },
          close: () => {},
        };
        request.result = db as IDBDatabase;
        request.onsuccess?.(new Event("success"));
      });
      return request as IDBOpenDBRequest;
    },
  } as IDBFactory;
}

describe("service worker JWT minting", () => {
  it("uses raw crypto.subtle.sign bytes instead of DER conversion", async () => {
    const source = await readFile(SW_PATH, "utf8");
    expect(source).not.toContain("derSignatureToJose");
    expect(source).toContain(
      "const signature = base64UrlEncode(new Uint8Array(signatureRaw));",
    );
  });

  it("encodes the JWT signature directly from sign() output bytes", async () => {
    const source = await readFile(SW_PATH, "utf8");
    expect(source).toContain("async function mintHttpToken()");
    expect(source).toContain("const signatureRaw = await crypto.subtle.sign(");
    const signatureBytes = new Uint8Array(Array.from({ length: 64 }, (_, i) => i));
    const indexedDB = createIndexedDbMock({
      h4ckath0n_device_private_key: { mock: "private-key" },
      h4ckath0n_device_id: "d1234567890123456789012345678901",
      h4ckath0n_user_id: "u1234567890123456789012345678901",
    });

    const cryptoMock = {
      subtle: {
        sign: async () => signatureBytes.buffer,
      },
    } as unknown as Crypto;

    const btoaMock = (value: string): string =>
      Buffer.from(value, "binary").toString("base64");

    const selfMock = {
      location: { origin: "https://example.com" },
      registration: {},
      clients: {},
      addEventListener: () => {},
    };

    const factory = new Function(
      "self",
      "indexedDB",
      "crypto",
      "TextEncoder",
      "btoa",
      `${source}; return { mintHttpToken };`,
    ) as (
      self: unknown,
      indexedDB: IDBFactory,
      crypto: Crypto,
      TextEncoder: typeof globalThis.TextEncoder,
      btoa: (value: string) => string,
    ) => { mintHttpToken: () => Promise<string> };

    const { mintHttpToken } = factory(
      selfMock,
      indexedDB,
      cryptoMock,
      TextEncoder,
      btoaMock,
    );
    const token = await mintHttpToken();

    const parts = token.split(".");
    expect(parts).toHaveLength(3);
    expect(parts[2]).toBe(toBase64Url(signatureBytes));
  });
});
