// Types for the Agents card-grid blueprint — mirrors backend/routes/agents.py models.

export interface Agent {
  id: string
  name: string
  description: string
  status: 'active' | 'paused' | 'error'
  model: string
  runs_today: number
  last_run: string
}
