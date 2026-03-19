# Privacy Policy

**karellen-rr-mcp** — MCP Server for rr Reverse Debugging

*Last updated: 2026-03-19*

## Summary

karellen-rr-mcp does not collect, transmit, or store any personal data. It runs
entirely on your local machine.

## Data Collection

This software does **not**:

- Collect or transmit any personal information
- Send telemetry, analytics, or usage data
- Make any network connections (other than the local stdio/TCP communication
  between the MCP server, rr, and GDB, all on localhost)
- Store any data beyond rr trace recordings, which are created by rr itself in
  its standard trace directory on your local filesystem

## Data Processing

All debugging operations (recording, replaying, inspecting program state) are
performed locally using rr and GDB. The MCP server acts as a local bridge between
the MCP client (e.g. Claude Code) and these tools. No data leaves your machine
through this software.

## Third-Party Services

This software does not integrate with any third-party services or APIs.

## Changes to This Policy

If this policy changes, the updated version will be published in the project
repository at
[https://github.com/karellen/karellen-rr-mcp](https://github.com/karellen/karellen-rr-mcp).

## Contact

If you have questions about this privacy policy, please open an issue at
[https://github.com/karellen/karellen-rr-mcp/issues](https://github.com/karellen/karellen-rr-mcp/issues)
or contact [supervisor@karellen.co](mailto:supervisor@karellen.co).
