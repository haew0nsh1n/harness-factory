import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

import { getPortalAuthMode, isEntraMode } from "@/lib/auth";

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "DELETE"]);
const SAFE_SEGMENT_RE = /^[A-Za-z0-9._-]+$/;

function invalidResponse(status: number, code: string, error: string): NextResponse {
  return NextResponse.json({ ok: false, code, error }, { status });
}

function getForwardedPath(rawPath: string[] | undefined): string | null {
  if (!rawPath || rawPath.length === 0) {
    return null;
  }

  for (const segment of rawPath) {
    if (
      segment.length === 0 ||
      segment === "." ||
      segment === ".." ||
      !SAFE_SEGMENT_RE.test(segment)
    ) {
      return null;
    }
  }

  return rawPath.map(encodeURIComponent).join("/");
}

function getUpstreamUrl(path: string, request: NextRequest): URL | null {
  const baseUrl = process.env.HF_API_BASE_URL;
  if (!baseUrl) {
    return null;
  }

  const upstream = new URL(`/api/${path}`, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  upstream.search = request.nextUrl.search;
  return upstream;
}

async function proxyRequest(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  if (!ALLOWED_METHODS.has(request.method)) {
    return invalidResponse(405, "method_not_allowed", "method not allowed");
  }

  const params = await context.params;
  const path = getForwardedPath(params.path);
  if (!path) {
    return invalidResponse(400, "invalid_path", "invalid control-plane path");
  }

  const upstream = getUpstreamUrl(path, request);
  if (!upstream) {
    return invalidResponse(500, "proxy_not_configured", "HF_API_BASE_URL is not configured");
  }

  const headers = new Headers({ accept: "application/json" });
  let body: string | undefined;

  if (request.method !== "GET") {
    body = await request.text();
    if (body) {
      try {
        JSON.parse(body);
      } catch {
        return invalidResponse(400, "invalid_json", "request body must be valid JSON");
      }
      headers.set("content-type", "application/json");
    }
  }

  if (getPortalAuthMode() === "development") {
    const organization = process.env.HF_DEV_ORGANIZATION;
    const subject = process.env.HF_DEV_SUBJECT;
    const roles = process.env.HF_DEV_ROLES;

    if (!organization || !subject || !roles) {
      return invalidResponse(
        500,
        "development_identity_missing",
        "Development identity headers are not configured on the server",
      );
    }

    headers.set("X-HF-Organization", organization);
    headers.set("X-HF-Subject", subject);
    headers.set("X-HF-Roles", roles);
  } else if (isEntraMode()) {
    const token = await getToken({
      req: request,
      secret: process.env.AUTH_SECRET,
    });
    const accessToken = typeof token?.accessToken === "string" ? token.accessToken : null;

    if (!accessToken) {
      const signInUrl = new URL("/api/auth/signin", request.url);
      signInUrl.searchParams.set(
        "callbackUrl",
        `${request.nextUrl.pathname}${request.nextUrl.search}`,
      );
      return NextResponse.redirect(signInUrl);
    }

    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(upstream, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "application/json";

  if (!contentType.includes("application/json")) {
    const passthrough = new Headers({ "content-type": contentType });
    const disposition = response.headers.get("content-disposition");
    if (disposition) {
      passthrough.set("content-disposition", disposition);
    }
    const length = response.headers.get("content-length");
    if (length) {
      passthrough.set("content-length", length);
    }
    const buffer = await response.arrayBuffer();
    return new NextResponse(buffer, {
      status: response.status,
      headers: passthrough,
    });
  }

  const responseBody = await response.text();

  return new NextResponse(responseBody, {
    status: response.status,
    headers: {
      "content-type": contentType,
    },
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  return proxyRequest(request, context);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  return proxyRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  return proxyRequest(request, context);
}
