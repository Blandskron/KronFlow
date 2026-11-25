import { environment } from '@env/environment';

export const API_BASE_URL = environment.apiUrl.replace(/\/$/, '');
export const OPERATIONAL_API_BASE_URL = environment.operationalApiUrl.replace(/\/$/, '');
export const AGENT_CORE_API_BASE_URL = environment.agentCoreApiUrl.replace(/\/$/, '');
