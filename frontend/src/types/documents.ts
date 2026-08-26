export type DocumentStatus = 'describing' | 'ready' | 'failed'

export interface Document {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  description: string | null
  status: DocumentStatus
  error: string | null
  uploaded_at: string
  described_at: string | null
}
