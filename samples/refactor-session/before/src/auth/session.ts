import { randomUUID } from "node:crypto";
import type { Response } from "express";
import { signToken } from "./jwt";
import { db } from "../db";

const SESSION_TTL_SECONDS = 60 * 60; // 1 hour

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatTimestamp(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

export async function issueSession(res: Response, userId: string): Promise<string> {
  const sessionId = randomUUID();
  const expiresAt = Date.now() + SESSION_TTL_SECONDS * 1000;
  await db.sessions.insert({ id: sessionId, userId, expiresAt });

  const token = signToken({ sid: sessionId, sub: userId }, SESSION_TTL_SECONDS);
  res.cookie("session", token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    maxAge: SESSION_TTL_SECONDS * 1000,
  });
  console.info(`session ${sessionId} issued, expires ${formatTimestamp(expiresAt)}`);
  return sessionId;
}

export async function revokeSession(sessionId: string): Promise<void> {
  await db.sessions.delete({ id: sessionId });
}
