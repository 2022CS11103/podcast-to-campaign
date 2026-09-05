const path = require("path");

const python = path.join(__dirname, ".venv", "bin", "python");

module.exports = {
  apps: [
    {
      name: "creatoros",
      cwd: __dirname,
      script: python,
      args: "-m uvicorn api.main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      instances: 1,
      exec_mode: "fork",
      env: {
        PORT: "8000",
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
