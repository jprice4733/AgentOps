// Types for the Wizard building block — mirrors backend/routes/wizard.py models.

export interface WizardSubmission {
  name: string
  category: string
  notes: string
}

export interface WizardResult {
  id: string
  summary: string
}
