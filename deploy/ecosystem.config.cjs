// PM2 ecosystem — supervises the docker compose stack as a single managed process.
//
// `pm2 start deploy/ecosystem.config.cjs` brings the stack up.
// `pm2 logs helios-stack` tails compose output.
// `pm2 startup && pm2 save` makes it survive VPS reboots.

const path = require("path");
const APP_ROOT = process.env.HELIOS_APP_ROOT || "/srv/helios/app";

module.exports = {
  apps: [
    {
      name: "helios-stack",
      script: "/usr/bin/docker",
      args: [
        "compose",
        "-f",
        path.join(APP_ROOT, "deploy/docker-compose.prod.yml"),
        "--env-file",
        "/srv/helios/.env",
        "up",
      ],
      cwd: APP_ROOT,
      // PM2 owns lifecycle; let docker compose manage container restarts internally.
      autorestart: true,
      max_restarts: 10,
      min_uptime: "30s",
      restart_delay: 5000,
      // Long-form output is best in the file logs; pm2 console gets the highlights.
      out_file: "/srv/helios/logs/stack.out.log",
      error_file: "/srv/helios/logs/stack.err.log",
      merge_logs: true,
      time: true,
      env: {
        COMPOSE_PROJECT_NAME: "helios",
        // Compose reads the rest from --env-file
      },
    },
  ],
};
