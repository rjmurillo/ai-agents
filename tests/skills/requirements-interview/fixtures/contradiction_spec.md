# Session Service Specification

## 1. Overview

The session service tracks signed-in devices for each account.

## 3. Limits

### 3.1 Session count

A user may hold at most 3 active sessions at one time.

### 3.2 Idle timeout

An idle session expires after 30 minutes.

## 5. Account policy

### 5.2 Concurrency

Each account supports up to 5 concurrent sessions.
