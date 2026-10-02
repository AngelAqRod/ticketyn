import { Layers3 } from 'lucide-react'
import { PageHeading } from '../components/PageHeading'

export function Placeholder({ title, description }: { title: string; description: string }) {
  return <><PageHeading title={title} description={description} />
    <div className="panel p-12 text-center"><Layers3 size={30} aria-hidden="true" className="mx-auto mb-4 text-slate-400" />
      <h2 className="font-medium text-slate-900">Próximamente</h2>
      <p className="mt-2 text-sm text-slate-500">Esta sección se incorporará en una siguiente etapa.</p>
    </div></>
}
