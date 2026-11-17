[한국어 (Korean)](SECURITY.ko.md) / [English](SECURITY.md)

# Security policy

## Reporting a vulnerability

Please do not post the details in a public issue.

Use GitHub's private reporting: the **Security** tab of this repository, then **Report a vulnerability**. If that button is not shown, open an issue that says only that you have a security report, and I will set up a private channel with you.

This is a one-person project. I will reply as soon as I can.

## Supported versions

The latest release and `main`.

## What the server touches

Useful when you judge the impact of a problem:

- It talks to the MCP client over stdio and makes no network connections. Installing it downloads the package and its three dependencies (`mcp`, `python-rtmidi`, `pydantic`).
- It asks for no macOS privacy permissions (Accessibility, Screen Recording, Automation). It opens one virtual CoreMIDI port, "LogicMCP", and sends Mackie Control messages to Logic through it.
- It writes only to `~/.logic-mcp/` (the plug-in cache), reads Logic's `Info.plist` for the version, and runs one external command, `pgrep`, to see whether Logic is running.
- It changes the Logic project that is open, by design. It never saves the project.
