const path = require("path");

module.exports = {
  apps: [
    {
      name: "creatoros",
      cwd: path.join(__dirname, "paywall"),
      script: path.join(__dirname, "paywall", "index.js"),
      interpreter: "node",
      instances: 1,
      exec_mode: "fork",
      env: {
        PORT: "8000",
        HOST: "127.0.0.1",
        NODE_ENV: "production",
      },
    },
  ],
};
