export interface TicketNumberConfig {
  id: number
  prefix: string
  separator: string
  next_number: number
  padding: number
}
export type TicketNumberChanges = Partial<Omit<TicketNumberConfig, 'id'>>
