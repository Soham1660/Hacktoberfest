import { randomUUID } from "node:crypto";
import type { Response } from "express";
import { signToken } from "./jwt";
import { db } from "../db";
import { formatTimestamp } from "../utils/time";

const SESSION_TTL_SECONDS = 60 * 60 * 24 * 30;

export async function issueSession(res: Response, userId: string): Promise<string> {
  const sessionId = randomUUID();
  const expiresAt = Date.now() + SESSION_TTL_SECONDS * 1000;
  await db.sessions.insert({ id: sessionId, userId, expiresAt });

  const token = signToken({ sid: sessionId, sub: userId }, SESSION_TTL_SECONDS);
  res.cookie("session", token, {
    secure: true,
    sameSite: "lax",
    maxAge: SESSION_TTL_SECONDS * 1000,
  });
  console.info(`session ${sessionId} issued, expires ${formatTimestamp(expiresAt)}`);
  return sessionId;
}

export async function revokeSession(sessionId: string): Promise<void> {
  await db.sessions.delete({ id: sessionId });
}
