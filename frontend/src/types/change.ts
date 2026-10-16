import type { NamedCatalog, Responsible } from './catalog'
export type ChangeStatus='SCHEDULED'|'EXECUTING'|'FINISHED'
export interface CompletionType extends NamedCatalog { description:string|null; applies_efficiency:boolean }
export interface Change {
 change_type_id:number|null;change_type:Pick<NamedCatalog,'id'|'name'|'active'>|null;
 id:number;reference:string;ticket_number:number;title:string;description:string;sector_id:number;node_id:number|null;manager_id:number;manager_name:string;department_id:number;department_name:string;support:{id:number;name:string}[];status:ChangeStatus;proposed_start:string;proposed_end:string;actual_start:string|null;actual_end:string|null;completion_type_id:number|null;completion_name:string|null;efficiency_eligible:boolean|null;final_notes:string|null;created_at:string;updated_at:string;sector:{id:number;name:string};node:{id:number;name:string}|null;internal_tickets:{id:number;reference:string;title:string}[];planned_seconds:number;actual_seconds:number|null;efficiency:string;efficiency_label:string;variation_percent:number|null;saved_seconds:number|null;exceeded_seconds:number|null;late_start:boolean
}
export interface ChangeUpdate {id:number;occurred_at:string;responsible_name:string;content:string}
export interface ChangeCatalogs { sectors:NamedCatalog[];nodes:NamedCatalog[];people:Responsible[];departments:NamedCatalog[];types:CompletionType[];changeTypes:NamedCatalog[] }
export interface ChangeSummary {
 kpis:{total:number;finished:number;scheduled:number;executing:number;average_seconds:number|null;total_seconds:number;evaluable:number;better:number;on_time:number;exceeded:number;not_evaluable:number;saved_seconds:number;exceeded_seconds:number;planned_evaluable_seconds:number;real_evaluable_seconds:number;late_starts:number;percentages:{better:number;on_time:number;exceeded:number}};
 change_types:ChangeRanking[];sectors:ChangeRanking[];nodes:ChangeRanking[];departments:ChangeRanking[];statuses:ChangeRanking[];completion_types:ChangeRanking[];participants:(ChangeRanking & {manager:number;support:number})[];trend:{start_at:string;count:number}[];granularity:'hour'|'day'|'week'|'month';generated_at:string
}
export interface ChangeRanking {id:number|null;label:string;count:number}
