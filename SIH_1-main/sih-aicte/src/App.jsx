import React, { useEffect, useMemo, useState } from 'react';

import {

  Activity, AlertTriangle, ArrowDownRight, ArrowRight, Bell, Building2, CalendarDays,

  Check, CheckCircle2, ChevronDown, CircleHelp, ClipboardCheck, Clock3, Download,

  Eye, FileCheck2, FileText, Filter, GraduationCap, LayoutDashboard, LogOut, Menu,

  MessageSquareText, Plus, Search, Settings, ShieldCheck, Upload, Users, X, XCircle

} from 'lucide-react';



const KEY = 'aicte_portal_v1';

const SESSION_KEY = 'aicte_portal_session_v1';

const API = import.meta.env.VITE_API_BASE_URL || 'https://summati.onrender.com';

async function backend(path, options={}) {

 const isForm=options.body instanceof FormData;

 const response=await fetch(`${API}${path}`,{credentials:'include',...options,headers:{...(isForm?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});

 const data=await response.json().catch(()=>({error:'The server returned an unreadable response.'}));

 if(!response.ok) throw new Error(data.error||`Request failed (${response.status})`);

 return data;

}

function mapBackendDocument(d){
  const rawStatus=String(d.upload_status||'Uploaded');
  const normalized=rawStatus.toLowerCase();
  let status='Pending';
  if(normalized.includes('superseded')||normalized.includes('archived')) status='Superseded';
  else if(normalized.includes('deficient')||normalized.includes('rejected')) status='Deficient';
  else if(normalized.includes('approved')||normalized.includes('verified')) status='Approved';
  else if(normalized.includes('manual review')||normalized.includes('flagged')||normalized.includes('duplicate')||normalized.includes('placeholder')||normalized.includes('unsigned')||normalized.includes('signature missing')||normalized.includes('seal missing')||normalized.includes('alteration')||normalized.includes('suspicious')||normalized.includes('needs review')) status='Needs Review';
  return {
    id: d.id,
    requirementId: d.requirement_id,
    name: d.document_name || d.file_name || 'Uploaded document',
    fileName: d.file_name || d.document_name || 'document',
    size: d.file_size || d.size || 0,
    status,
    rawStatus,
    remarks: d.remarks || ''
  };
}

function mapBackendApplication(a, currentSession=null){
  return {
    id:a.tracking_id||String(a.id),
    backendId:a.id,
    institution:a.institution_name||'Institution',
    type:a.application_type||'New Institution',
    state:a.state||'—',
    contact:a.contact_email || (currentSession?.role==='institution' ? currentSession.email : ''),
    submittedAt:(a.submission_date||'').slice(0,10),
    deadline:(a.deadline||'').slice(0,10),
    status:a.status||'Draft',
    stage:a.current_stage||'Draft',
    officer:a.assigned_officer||'Unassigned',
    remarks:a.remarks||'',
    documents:Array.isArray(a.documents) ? a.documents.map(mapBackendDocument) : []
  };
}



const today = () => new Date().toISOString().slice(0, 10);

const addDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

const starter = [

  { id: 'AICTE-2026-1001', institution: 'North Valley Institute of Technology', type: 'New Institution', state: 'Karnataka', contact: 'office@northvalley.edu.in', submittedAt: addDays(-8), deadline: addDays(5), status: 'Pending', stage: 'Initial Scrutiny', officer: 'Unassigned', remarks: '', documents: [{id:'d1',name:'Certificate of Incorporation',fileName:'incorporation-certificate.pdf',size:245760,status:'Pending',remarks:''},{id:'d2',name:'Land Ownership Document',fileName:'land-records.pdf',size:419840,status:'Pending',remarks:''},{id:'d3',name:'Faculty Details',fileName:'faculty-details.xlsx',size:98304,status:'Pending',remarks:''}] },

  { id: 'AICTE-2026-1002', institution: 'Greenfield College of Engineering', type: 'Extension of Approval', state: 'Tamil Nadu', contact: 'admin@greenfield.edu.in', submittedAt: addDays(-12), deadline: addDays(-1), status: 'Deficient', stage: 'Document Verification', officer: 'Ananya Rao', remarks: 'Please upload the latest building safety certificate.', documents: [{id:'d4',name:'Previous Approval Letter',fileName:'previous-approval.pdf',size:301056,status:'Approved',remarks:''},{id:'d5',name:'Building Safety Certificate',fileName:'building-safety.pdf',size:182272,status:'Deficient',remarks:'Certificate validity has expired.'}] },

  { id: 'AICTE-2026-1003', institution: 'Riverbend School of Applied Sciences', type: 'Increase in Intake', state: 'Maharashtra', contact: 'registrar@riverbend.edu.in', submittedAt: addDays(-4), deadline: addDays(9), status: 'In Review', stage: 'Technical Review', officer: 'Rahul Menon', remarks: '', documents: [{id:'d6',name:'Faculty Details',fileName:'faculty-list.pdf',size:204800,status:'Approved',remarks:''},{id:'d7',name:'Infrastructure Report',fileName:'infrastructure-report.pdf',size:350208,status:'Pending',remarks:''}] },

  { id: 'AICTE-2026-1004', institution: 'Sunrise Polytechnic Institute', type: 'New Course', state: 'Telangana', contact: 'principal@sunrise.edu.in', submittedAt: addDays(-20), deadline: addDays(-4), status: 'Approved', stage: 'Decision Issued', officer: 'Ananya Rao', remarks: 'Application reviewed and approved.', documents: [{id:'d8',name:'Application Form',fileName:'application-form.pdf',size:155648,status:'Approved',remarks:''},{id:'d9',name:'Infrastructure Report',fileName:'infra.pdf',size:266240,status:'Approved',remarks:''}] },

];

const readData = () => { try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : starter; } catch { return starter; } };

const statusClass = (s) => ({Approved:'approved',Pending:'pending','Needs Review':'review','In Review':'review',Deficient:'deficient',Rejected:'rejected','Correction Requested':'deficient'}[s] || 'pending');

const fmtDate = (s) => s ? new Date(`${s}T00:00:00`).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'}) : '—';

const formatBytes = (n) => n < 1024 ? `${n} B` : `${(n/1024).toFixed(0)} KB`;



function Brand({small=false}) { return <div className={`brand ${small?'brand-small':''}`}><div className="brand-mark"><ShieldCheck size={22}/></div><div><strong>AICTE<span>Flow</span></strong><small>Approval & Compliance</small></div></div>; }

function Status({value}) { return <span className={`status status-${statusClass(value)}`}><i />{value}</span>; }

function Metric({label,value,detail,icon:Icon,tone}) { return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={19}/></div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-detail">{detail}</div></div>; }

function Modal({title,children,onClose,wide=false}) { return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className={`modal ${wide?'modal-wide':''}`}><header className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close"><X size={19}/></button></header>{children}</section></div>; }



export default function App() {

  const [session,setSession] = useState(null); // Start at login on every fresh page load; sign in to open a dashboard.

  const [applications,setApplications] = useState(readData);

  const [page,setPage] = useState('dashboard');

  const [selectedId,setSelectedId] = useState(null);

  const [search,setSearch] = useState('');

  const [statusFilter,setStatusFilter] = useState('All statuses');

  const [toast,setToast] = useState('');

  const [showNew,setShowNew] = useState(false);

  const [showUpload,setShowUpload] = useState(false);

  const [mobileOpen,setMobileOpen] = useState(false);

  const [showProfile,setShowProfile] = useState(false);

  const [reviewDoc,setReviewDoc] = useState(null);

  const [reviewRemark,setReviewRemark] = useState('');

  const [decisionRemark,setDecisionRemark] = useState('');

  const [form,setForm] = useState({institution:'',type:'New Institution',state:'Karnataka',contact:'',notes:''});

  const [files,setFiles] = useState([]);

  const [uploadAppId,setUploadAppId] = useState('');

  const [uploadFiles,setUploadFiles] = useState([]);

  const [integrityReviews,setIntegrityReviews] = useState([]);
  const [integrityLoading,setIntegrityLoading] = useState(false);



  useEffect(()=>{ localStorage.setItem(KEY,JSON.stringify(applications)); },[applications]);

  useEffect(()=>{
    let active=true;
    backend('/api/auth/session').then(result=>{
      if(!active||!result.authenticated||!result.user) return;
      const user=result.user;
      const restored={role:user.role,email:user.email,display:user.role==='officer'?'AICTE Officer':user.role==='committee'?'EVC Committee Member':user.role==='authority'?'Regulatory Authority':(user.institution_name||user.email.split('@')[0])};
      setSession(restored);localStorage.setItem(SESSION_KEY,JSON.stringify(restored));
    }).catch(()=>{});
    return ()=>{active=false;};
  },[]);

  useEffect(()=>{ if(!session)return; let active=true; refreshApplications(session).catch(err=>{if(active)setToast(`Could not refresh server applications: ${err.message}`);}); return ()=>{active=false;}; },[session?.email,session?.role]);

  useEffect(()=>{
    if(session?.role!=='officer') { setIntegrityReviews([]); return; }
    let active=true;
    setIntegrityLoading(true);
    backend('/api/integrity-reviews').then(data=>{if(active)setIntegrityReviews(data.reviews||[]);})
      .catch(err=>{if(active)setToast(`Could not load document integrity review queue: ${err.message}`);})
      .finally(()=>{if(active)setIntegrityLoading(false);});
    return ()=>{active=false;};
  },[session?.role,session?.email]);

  useEffect(()=>{ if(toast){const t=setTimeout(()=>setToast(''),3200);return ()=>clearTimeout(t);} },[toast]);

  const isOfficer = session?.role === 'officer';
  const isCommittee = session?.role === 'committee';
  const isAuthority = session?.role === 'authority';
  const canSeeAll = isOfficer || isCommittee || isAuthority;

  const mine = useMemo(()=>canSeeAll?applications:applications.filter(a=>a.contact===session?.email),[applications,canSeeAll,session]);

  const selected = applications.find(a=>a.id===selectedId) || null;



const filtered = useMemo(() => mine.filter(a => {

  const q = search.toLowerCase().trim();



  const searchFields = canSeeAll

    ? [a.id, a.institution, a.type, a.state, a.officer, a.stage]

    : [a.id, a.type, a.status];



  const hit = !q || searchFields.some(v =>

    String(v || '').toLowerCase().includes(q)

  );



  return hit &&

    (statusFilter === 'All statuses' || a.status === statusFilter);

}), [mine, search, statusFilter, canSeeAll]);



  const allDocs = mine.flatMap(a=>a.documents.map(d=>({...d,applicationId:a.id,institution:a.institution})));

  const overdue = mine.filter(a=>!['Approved','Rejected'].includes(a.status)&&a.deadline&&a.deadline<today()).length;

  const counts = {total:mine.length,pending:mine.filter(a=>a.status==='Pending').length,review:mine.filter(a=>a.status==='In Review').length,approved:mine.filter(a=>a.status==='Approved').length,deficient:mine.filter(a=>a.status==='Deficient').length,overdue};



  async function login(role,email,password,mode,institutionName) {

 try {

  const data=mode==='register'?await backend('/api/auth/register',{method:'POST',body:JSON.stringify({email,password,institution_name:institutionName})}):await backend('/api/auth/login',{method:'POST',body:JSON.stringify({email,password,role})});

  const user=data.user; const s={role:user.role,email:user.email,display:user.role==='officer'?'AICTE Officer':user.role==='committee'?'EVC Committee Member':user.role==='authority'?'Regulatory Authority':(user.institution_name||user.email.split('@')[0])};

  setSession(s);localStorage.setItem(SESSION_KEY,JSON.stringify(s));

  await refreshApplications(s);

  setPage('dashboard');setToast(`Welcome to the ${s.role==='officer'?'AICTE Officer':s.role==='committee'?'EVC Committee':s.role==='authority'?'Regulatory Authority':'Institution'} Portal`); return null;

 } catch(err){return {error:err.message};}

}

  async function logout(){try{await backend('/api/auth/logout',{method:'POST',body:JSON.stringify({})});}catch{}setSession(null);localStorage.removeItem(SESSION_KEY);setPage('dashboard');setSelectedId(null);}

  function notify(msg){setToast(msg);}

  async function refreshApplications(sessionOverride=session){
    const list=await backend('/api/applications');
    const mapped=(list.applications||[]).map(a=>mapBackendApplication(a,sessionOverride));
    const withDocuments=await Promise.all(mapped.map(async app=>{
      try{
        const result=await backend(`/api/applications/${app.backendId}/documents`);
        return {...app,documents:(result.documents||[]).map(mapBackendDocument)};
      }catch{
        return app;
      }
    }));
    setApplications(withDocuments);
    return withDocuments;
  }

  async function uploadFilesToApplication(application, selectedFiles){
    const requirementResult=await backend(`/api/document-requirements?application_type=${encodeURIComponent(application.type)}`);
    const requirements=requirementResult.documents||[];
    const existingResult=await backend(`/api/applications/${application.backendId}/documents`);
    const existingDocs=existingResult.documents||[];
    const existingByRequirement=new Map(existingDocs.map(d=>[Number(d.requirement_id),d]));
    const pendingRequirements=requirements.filter(r=>{
      const old=existingByRequirement.get(Number(r.id));
      return !old || ['deficient','rejected'].includes(String(old.upload_status||'').toLowerCase());
    });
    if(selectedFiles.length>pendingRequirements.length){
      throw new Error(`There are only ${pendingRequirements.length} unfilled or deficient document requirements available for upload. Upload fewer files or review existing documents.`);
    }
    for(let i=0;i<selectedFiles.length;i++){
      const file=selectedFiles[i];
      const requirement=pendingRequirements[i];
      const ext=(file.name.split('.').pop()||'').toLowerCase();
      if(!['pdf','png','jpg','jpeg'].includes(ext)){
        throw new Error(`${file.name}: the server accepts PDF, PNG, JPG or JPEG files only.`);
      }
      const body=new FormData();
      body.append('requirement_id',String(requirement.id));
      body.append('file',file);
      const prior=existingByRequirement.get(Number(requirement.id));
      const endpoint=prior && ['deficient','rejected'].includes(String(prior.upload_status||'').toLowerCase())
        ? `/api/applications/${application.backendId}/documents/${prior.id}/replace`
        : `/api/applications/${application.backendId}/documents`;
      await backend(endpoint,{method:'POST',body});
    }
  }

  async function createApplication(e){
    e.preventDefault();
    if(!form.institution.trim()||(isOfficer&&!form.contact.trim())){
      notify('Please enter the institution name and contact email.');
      return;
    }
    let createdApplication=null;
    try{
      const result=await backend('/api/applications',{
        method:'POST',
        body:JSON.stringify({institution_name:form.institution.trim(),application_type:form.type,state:form.state,remarks:form.notes.trim()})
      });
      const list=await backend('/api/applications');
      const mapped=(list.applications||[]).map(a=>mapBackendApplication(a,session));
      createdApplication=mapped.find(x=>Number(x.backendId)===Number(result.application_id))||{
        id:result.tracking_id||String(result.application_id),
        backendId:result.application_id,
        institution:form.institution.trim(),
        type:form.type,
        state:form.state,
        contact:session?.email||'',
        submittedAt:today(),
        deadline:(result.deadline||'').slice(0,10),
        status:'Draft',
        stage:'Draft',
        officer:'Unassigned',
        remarks:'',
        documents:[]
      };
      if(files.length) await uploadFilesToApplication(createdApplication,files);
      const refreshed=await refreshApplications();
      const finalCreated=refreshed.find(x=>Number(x.backendId)===Number(result.application_id))||createdApplication;
      setSelectedId(finalCreated.id);
      setPage('application-detail');
      setShowNew(false);
      setForm({institution:'',type:'New Institution',state:'Karnataka',contact:session?.role==='institution'?session.email:'',notes:''});
      setFiles([]);
      notify(files.length ? 'Application created and documents uploaded successfully.' : 'Application draft created. You can add documents from the application details.');
    }catch(err){
      if(createdApplication){
        try{await refreshApplications();}catch{}
        setSelectedId(createdApplication.id);
        setPage('application-detail');
        setShowNew(false);
        notify(`Application was created, but a document upload failed: ${err.message}`);
      }else{
        notify(`Could not create application: ${err.message}`);
      }
    }
  }

  async function uploadDocuments(e){
    e.preventDefault();
    if(!uploadAppId||!uploadFiles.length){
      notify('Choose an application and at least one file.');
      return;
    }
    const application=applications.find(a=>a.id===uploadAppId);
    if(!application?.backendId){
      notify('Could not identify this application on the server. Refresh the page and try again.');
      return;
    }
    try{
      await uploadFilesToApplication(application,uploadFiles);
      await refreshApplications();
      if(isOfficer) await refreshIntegrityReviews();
      setShowUpload(false);
      setUploadFiles([]);
      notify('Documents uploaded and saved on the server.');
    }catch(err){
      try{await refreshApplications();}catch{}
      notify(`Document upload failed: ${err.message}`);
    }
  }


  async function refreshIntegrityReviews(){
    if(session?.role!=='officer') return [];
    const data=await backend('/api/integrity-reviews');
    const reviews=data.reviews||[];
    setIntegrityReviews(reviews);
    return reviews;
  }

  function openIntegrityFile(applicationId,documentId){
    if(!applicationId||!documentId){notify('Original document location is unavailable.');return;}
    window.open(`${API}/api/applications/${applicationId}/documents/${documentId}/file`,'_blank','noopener,noreferrer');
  }

  async function updateIntegrityReview(review,action){
    try{
      if(action==='deficient'){
        await backend(`/api/applications/${review.application_id}/documents/${review.document_id}/verify`,{
          method:'PUT',body:JSON.stringify({decision:'Deficient',performed_by:session.email,remarks:`Marked deficient after automated screening. ${review.reason}`})
        });
        await backend(`/api/integrity-reviews/${review.id}`,{
          method:'PUT',body:JSON.stringify({status:'Referred for Further Verification',officer_remarks:`Document marked deficient. ${review.reason}`})
        });
        notify('Document and application marked deficient; review action saved.');
      }else{
        const status=action==='investigate'?'Under Investigation':'Cleared — No Malpractice Established';
        await backend(`/api/integrity-reviews/${review.id}`,{
          method:'PUT',body:JSON.stringify({status,officer_remarks:action==='investigate'?'Officer is investigating the screening flag.':'Officer reviewed the flag and cleared it; retain the review record for audit.'})
        });
        notify(action==='investigate'?'Review moved to investigation.':'Screening flag cleared by officer.');
      }
      await Promise.all([refreshApplications(),refreshIntegrityReviews()]);
    }catch(err){notify(`Could not save review action: ${err.message}`);}
  }

  async function updateApp(id,patch,reason=''){
    const appRecord=applications.find(a=>a.id===id);
    if(!appRecord?.backendId){notify('Application is not connected to the server.');return;}
    try{
      if(Object.prototype.hasOwnProperty.call(patch,'officer')){
        if(!reason.trim()){notify('Enter a reason in Review remarks before assigning or reassigning an officer.');return;}
        await backend(`/api/applications/${appRecord.backendId}/assign`,{method:'PUT',body:JSON.stringify({assigned_officer:patch.officer,reason:reason.trim()})});
      }
      if(Object.prototype.hasOwnProperty.call(patch,'stage')){
        if(!reason.trim()){notify('Enter a reason in Review remarks before changing the workflow stage.');return;}
        await backend(`/api/applications/${appRecord.backendId}/stage`,{method:'PUT',body:JSON.stringify({current_stage:patch.stage,reason:reason.trim()})});
      }
      if(Object.prototype.hasOwnProperty.call(patch,'remarks')){
        await backend(`/api/applications/${appRecord.backendId}/remarks`,{method:'PUT',body:JSON.stringify({remarks:patch.remarks})});
      }
      await refreshApplications();
      notify('Application changes saved to the server.');
    }catch(err){notify(`Could not save application changes: ${err.message}`);}
  }

  async function reviewDocument(appId,docId,status,remarks){
    const application=applications.find(a=>a.id===appId);
    if(!application?.backendId){notify('Could not find this application on the server.');return;}
    const decision=status==='Approved'?'Verified':status==='Deficient'?'Deficient':'Rejected';
    const finalRemark=remarks||(decision==='Verified'?'Document reviewed by officer.':'Please upload a corrected, verifiable document.');
    try{
      await backend(`/api/applications/${application.backendId}/documents/${docId}/verify`,{
        method:'PUT',body:JSON.stringify({decision,performed_by:session.email,remarks:finalRemark})
      });
      await refreshApplications();
      setReviewDoc(null);setReviewRemark('');
      notify(`Document review saved: ${status}.`);
    }catch(err){notify(`Could not save document review: ${err.message}`);}
  }

  async function decide(app,status,remarks){
    if(!app.backendId){notify('Application is not connected to the server.');return;}
    const finalRemark=String(remarks||'').trim();
    if(!finalRemark){notify('Review remarks are required for an application decision.');return;}
    try{
      if(status==='Deficient'){
        await backend(`/api/applications/${app.backendId}/stage`,{method:'PUT',body:JSON.stringify({current_stage:'Deficiency Raised',reason:finalRemark})});
        await backend(`/api/applications/${app.backendId}/remarks`,{method:'PUT',body:JSON.stringify({remarks:finalRemark})});
      }else{
        await backend(`/api/applications/${app.backendId}/decision`,{method:'PUT',body:JSON.stringify({decision:status,performed_by:session.email,remarks:finalRemark})});
      }
      await refreshApplications();setSelectedId(app.id);notify(`Application ${status.toLowerCase()} saved to the server.`);
    }catch(err){notify(`Could not save the decision: ${err.message}`);}
  }

  async function submitApplication(app){
    if(!app?.backendId){notify('Application is not connected to the server.');return;}
    try{
      const result=await backend(`/api/applications/${app.backendId}/submit`,{method:'POST',body:JSON.stringify({})});
      await refreshApplications();notify(result.message||'Application submitted for review.');
    }catch(err){notify(`Submission not completed: ${err.message}`);}
  }

  function exportCsv(){const rows=[['Application ID','Institution','Type','State','Submission date','Deadline','Status','Stage','Officer'],...filtered.map(a=>[a.id,a.institution,a.type,a.state,a.submittedAt,a.deadline,a.status,a.stage,a.officer])];const csv=rows.map(r=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const link=document.createElement('a');link.href=url;link.download='aicte-applications.csv';link.click();URL.revokeObjectURL(url);notify('Application report exported.');}

  if (!session) {

  return <Login onLogin={login} />;

}

  const nav = isOfficer ? [
    {id:'dashboard',label:'Overview',icon:LayoutDashboard},{id:'applications',label:'Applications',icon:FileText},{id:'documents',label:'Document verification',icon:ClipboardCheck},{id:'operations',label:'EVC & compliance',icon:Settings},{id:'alerts',label:'Alerts & deadlines',icon:Bell},{id:'reports',label:'Reports',icon:Activity}
  ] : isCommittee ? [
    {id:'dashboard',label:'Committee overview',icon:LayoutDashboard},{id:'applications',label:'Assigned cases',icon:FileText},{id:'operations',label:'EVC management',icon:ClipboardCheck}
  ] : isAuthority ? [
    {id:'dashboard',label:'Authority overview',icon:LayoutDashboard},{id:'applications',label:'Cases',icon:FileText},{id:'operations',label:'Compliance overview',icon:ClipboardCheck},{id:'alerts',label:'Alerts & deadlines',icon:Bell},{id:'reports',label:'Reports',icon:Activity}
  ] : [
    {id:'dashboard',label:'My overview',icon:LayoutDashboard},{id:'applications',label:'My applications',icon:FileText},{id:'documents',label:'My documents',icon:ClipboardCheck},{id:'operations',label:'My compliance',icon:Settings}
  ];

  const pageTitle = ({dashboard:isOfficer?'Officer overview':isCommittee?'Committee overview':isAuthority?'Authority overview':'Institution overview',applications:canSeeAll?'Applications':'My applications',documents:isOfficer?'Document verification':'My documents',operations:isOfficer?'EVC & compliance':isCommittee?'EVC management':isAuthority?'Compliance overview':'My compliance',alerts:'Alerts & deadlines',reports:'Reports','application-detail':'Application details'})[page] || 'Overview';



  return <div className="app-shell">

    <aside className={`sidebar ${mobileOpen?'sidebar-open':''}`}>

      <div className="sidebar-brand"><Brand/></div>

      <div className="portal-tag"><span className={isOfficer||isCommittee||isAuthority?'tag-officer':'tag-institution'}>{isOfficer?'OFFICER PORTAL':isCommittee?'COMMITTEE PORTAL':isAuthority?'AUTHORITY PORTAL':'INSTITUTION PORTAL'}</span></div>

      <div className="nav-caption">WORKSPACE</div>

      <nav className="side-nav">{nav.map(item=><button key={item.id} className={`nav-item ${page===item.id||(page==='application-detail'&&item.id==='applications')?'active':''}`} onClick={()=>{setPage(item.id);setSelectedId(null);setMobileOpen(false);}}><item.icon size={18}/><span>{item.label}</span>{item.id==='alerts'&&overdue>0&&<b className="nav-count">{overdue}</b>}</button>)}</nav>

      <div className="sidebar-bottom"><div className="help-card"><div className="help-icon"><CircleHelp size={18}/></div><strong>Need assistance?</strong><p>{isOfficer?'Review the workflow guide and officer checklist.':'Find guidance for submitting your application.'}</p><button onClick={()=>notify('Help centre: contact support@aicte.gov.in in this demo.')}>Open help centre <ArrowRight size={14}/></button></div><button className="nav-item logout" onClick={logout}><LogOut size={18}/><span>Sign out</span></button></div>

    </aside>

    <div className="main-column">

      <header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={()=>setMobileOpen(v=>!v)}><Menu size={20}/></button><div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{pageTitle}</strong></div></div><div className="topbar-right"><div className="secure-label"><span className="secure-dot"/> Secure workspace</div><button className="icon-button notification-button" onClick={()=>setPage(isOfficer||isAuthority?'alerts':'applications')} aria-label="Notifications"><Bell size={19}/>{overdue>0&&<i/>}</button><div className="profile-wrap"><button className="profile-button" onClick={()=>setShowProfile(v=>!v)}><span className="avatar">{isOfficer?'AO':session.display.slice(0,2).toUpperCase()}</span><span className="profile-text"><strong>{session.display}</strong><small>{isOfficer?'AICTE Officer':isCommittee?'EVC Committee Member':isAuthority?'Regulatory Authority':'Institution user'}</small></span><ChevronDown size={15}/></button>{showProfile&&<div className="profile-menu"><div className="profile-menu-head">Signed in as<br/><b>{session.email}</b></div><button onClick={()=>{setShowProfile(false);logout();}}><LogOut size={16}/> Sign out</button></div>}</div></div></header>

      <main className="content-area">

        {page==='dashboard'&&<>

          <div className="page-heading"><div><div className="eyebrow">{canSeeAll?'REGULATORY WORKSPACE':'INSTITUTION WORKSPACE'}</div><h1>{isOfficer?'Approval overview':isCommittee?'Committee overview':isAuthority?'Authority overview':'Welcome back'}</h1><p>{canSeeAll?'Monitor applications, compliance checks and service-level deadlines.':'Track your submissions and respond to document requirements.'}</p></div>{canSeeAll?<button className="btn btn-outline" onClick={exportCsv}><Download size={16}/> Export report</button>:session.role==='institution'&&<button className="btn btn-primary" onClick={()=>setShowNew(true)}><Plus size={17}/> New application</button>}</div>

          <div className="welcome-banner"><div className="banner-symbol"><ShieldCheck size={25}/></div><div><strong>{isOfficer?'Application oversight, in one place':'Your approval journey, made clearer'}</strong><p>{isOfficer?'Review queue, document compliance and approaching deadlines are brought together here.':'Submit complete applications, keep documents current and follow every status update.'}</p></div><div className="banner-meta"><span>WORKING DATE</span><strong>{fmtDate(today())}</strong></div></div>

          <div className="metrics-grid"><Metric label={isOfficer?'Total applications':'My applications'} value={counts.total} detail="All workflow stages" icon={FileText} tone="navy"/><Metric label="Pending review" value={counts.pending} detail="Awaiting initial action" icon={Clock3} tone="orange"/><Metric label={isOfficer?'In review':'Documents needed'} value={isOfficer?counts.review:counts.deficient} detail={isOfficer?'Under officer assessment':'Needs your attention'} icon={Activity} tone="peach"/><Metric label="Approved" value={counts.approved} detail="Decision issued" icon={CheckCircle2} tone="green"/><Metric label="Deficient" value={counts.deficient} detail="Correction required" icon={AlertTriangle} tone="red"/><Metric label="SLA breach" value={overdue} detail="Past the target deadline" icon={ArrowDownRight} tone="rose"/></div>

          <div className="dashboard-grid"><section className="panel applications-panel"><div className="panel-heading"><div><h2>{isOfficer?'Recent applications':'Recent submissions'}</h2><p>{isOfficer?'Latest activity across institutions':'Your latest application activity'}</p></div><button className="text-button" onClick={()=>setPage('applications')}>View all <ArrowRight size={15}/></button></div><ApplicationTable items={[...filtered].sort((a,b)=>b.submittedAt.localeCompare(a.submittedAt)).slice(0,5)} onOpen={a=>{setSelectedId(a.id);setPage('application-detail')}} compact empty="No applications found yet."/></section>

          <section className="panel deadline-panel"><div className="panel-heading"><div><h2>Deadline watch</h2><p>Items needing attention</p></div><span className="panel-heading-icon"><CalendarDays size={18}/></span></div><div className="deadline-list">{mine.filter(a=>!['Approved','Rejected'].includes(a.status)).sort((a,b)=>(a.deadline||'').localeCompare(b.deadline||'')).slice(0,4).map(a=><button className="deadline-item" key={a.id} onClick={()=>{setSelectedId(a.id);setPage('application-detail')}}><span className={`deadline-date ${a.deadline<today()?'late':''}`}><b>{a.deadline?new Date(`${a.deadline}T00:00:00`).getDate():'—'}</b><small>{a.deadline?new Date(`${a.deadline}T00:00:00`).toLocaleDateString('en-IN',{month:'short'}):'No date'}</small></span><span className="deadline-info"><strong>{a.institution}</strong><small>{a.id}</small></span><span className={`deadline-state ${a.deadline<today()?'late':''}`}>{!a.deadline?'Awaiting AICTE date':a.deadline<today()?'Overdue':`${Math.ceil((new Date(`${a.deadline}T00:00:00`)-new Date(`${today()}T00:00:00`))/86400000)}d left`}</span></button>)}{mine.filter(a=>!['Approved','Rejected'].includes(a.status)).length===0&&<div className="empty-state small-empty"><CalendarDays size={24}/><p>No active deadlines.</p></div>}</div><button className="deadline-footer" onClick={()=>setPage(isOfficer||isAuthority?'alerts':'applications')}>View deadline schedule <ArrowRight size={15}/></button></section></div>

          <section className="panel workflow-panel"><div className="panel-heading"><div><h2>Approval workflow</h2><p>Typical application journey</p></div><span className="muted-note">PROCESS OVERVIEW</span></div><div className="workflow-steps">{[{n:'01',title:'Submission',desc:'Institution submits form and documents',icon:Upload},{n:'02',title:'Initial scrutiny',desc:'Required fields and files checked',icon:FileCheck2},{n:'03',title:'Officer review',desc:'Compliance and technical assessment',icon:Users},{n:'04',title:'Decision',desc:'Decision and notification recorded',icon:CheckCircle2}].map((s,i)=><div className="workflow-step" key={s.n}><div className="workflow-icon"><s.icon size={19}/></div><span className="workflow-number">STEP {s.n}</span><strong>{s.title}</strong><p>{s.desc}</p>{i<3&&<ArrowRight className="workflow-arrow" size={16}/>}</div>)}</div></section>

        </>}

        {page==='applications'&&<><div className="page-heading"><div><div className="eyebrow">RECORDS & TRACKING</div><h1>{isOfficer?'Applications':'My applications'}</h1><p>{isOfficer?'Search, assign and manage institution approval requests.':'Review the progress and requirements for each submission.'}</p></div><div className="heading-actions">

  {isOfficer && (

    <button className="btn btn-outline" onClick={exportCsv}>

      <Download size={16}/> Export CSV

    </button>

  )}

  {!canSeeAll && (

    <button className="btn btn-primary" onClick={() => setShowNew(true)}>

      <Plus size={17}/> New application

    </button>

  )}

</div></div><div className="panel table-panel"><div className="table-toolbar"><div className="search-box"><Search size={17}/><input placeholder={isOfficer ? "Search institution, ID, type…" : "Search my applications by ID or type…"} value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button onClick={()=>setSearch('')}><X size={14}/></button>}</div><div className="filter-box"><Filter size={16}/><select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option>All statuses</option>{['Pending','In Review','Deficient','Approved','Rejected'].map(s=><option key={s}>{s}</option>)}</select></div><span className="result-count">{filtered.length} record{filtered.length!==1?'s':''}</span></div><ApplicationTable items={filtered} onOpen={a=>{setSelectedId(a.id);setPage('application-detail')}} empty="No matching applications. Try a different search or submit a new application."/></div></>}

        {page==='documents'&&<><div className="page-heading"><div><div className="eyebrow">DOCUMENT COMPLIANCE</div><h1>{isOfficer?'Document verification':'My documents'}</h1><p>{isOfficer?'Review uploaded evidence and record verification outcomes.':'View document status and upload requested files.'}</p></div>{!isOfficer&&<button className="btn btn-primary" onClick={()=>{setUploadAppId(mine[0]?.id||'');setShowUpload(true)}}><Upload size={16}/> Upload documents</button>}</div>{isOfficer&&<section className="panel integrity-panel"><div className="panel-heading"><div><h2>Potential integrity flags</h2><p>Exact/near duplicates, sample markers and signature/seal checks require human review; these are risk signals, not proof of fraud.</p></div><button className="btn btn-outline btn-small" onClick={()=>refreshIntegrityReviews().catch(err=>notify(`Could not refresh review queue: ${err.message}`))}>Refresh queue</button></div>{integrityLoading&&<p className="muted-text">Loading review queue…</p>}{!integrityLoading&&integrityReviews.filter(r=>!['Closed','Cleared — No Malpractice Established'].includes(r.status)).length===0&&<div className="empty-state"><ShieldCheck size={28}/><p>No open integrity flags. New duplicate or document-content warnings will appear here.</p></div>}<div className="integrity-list">{integrityReviews.filter(r=>!['Closed','Cleared — No Malpractice Established'].includes(r.status)).map(r=><article className="integrity-item" key={r.id}><div className="integrity-item-main"><div className="integrity-item-heading"><strong>{r.flag_category}</strong><Status value={r.status.includes('Pending')?'Deficient':r.status==='Under Investigation'?'In Review':r.status}/></div><p>{r.reason}</p><small>{r.institution_name} · {r.tracking_id||`Application ${r.application_id}`} · {r.document_name}</small>{r.matching_document_name&&<small className="integrity-match">Possible match: {r.matching_document_name} (application {r.matching_application_id||'unknown'})</small>}</div><div className="integrity-item-actions"><button className="btn btn-outline btn-small" onClick={()=>openIntegrityFile(r.application_id,r.document_id)}><Eye size={14}/> Open uploaded file</button>{r.matching_document_id&&r.matching_application_id&&<button className="btn btn-outline btn-small" onClick={()=>openIntegrityFile(r.matching_application_id,r.matching_document_id)}><Eye size={14}/> Open possible match</button>}{!['Under Investigation','Referred for Further Verification'].includes(r.status)&&<button className="btn btn-outline btn-small" onClick={()=>updateIntegrityReview(r,'investigate')}><Search size={14}/> Investigate</button>}{r.status!=='Referred for Further Verification'&&<button className="btn btn-danger btn-small" onClick={()=>updateIntegrityReview(r,'deficient')}><AlertTriangle size={14}/> Mark deficient</button>}<button className="btn btn-success btn-small" onClick={()=>updateIntegrityReview(r,'clear')}>Clear flag</button></div></article>)}</div></section>}<div className="document-summary"><div><span className="doc-summary-icon orange-bg"><Clock3 size={19}/></span><span><small>Pending</small><strong>{allDocs.filter(d=>d.status==='Pending').length}</strong></span></div><div><span className="doc-summary-icon green-bg"><CheckCircle2 size={19}/></span><span><small>Approved</small><strong>{allDocs.filter(d=>d.status==='Approved').length}</strong></span></div><div><span className="doc-summary-icon red-bg"><XCircle size={19}/></span><span><small>Deficient</small><strong>{allDocs.filter(d=>d.status==='Deficient').length}</strong></span></div></div><div className="document-grid">{mine.flatMap(a=>a.documents.map(d=>({...d,applicationId:a.id,backendApplicationId:a.backendId,institution:a.institution,appStatus:a.status}))).map(d=><article className="document-card" key={d.id}><div className="document-card-top"><div className="file-icon"><FileText size={21}/></div><Status value={d.status}/></div><h3>{d.name}</h3><p className="doc-institution">{d.institution}</p><div className="doc-file-name"><FileCheck2 size={14}/><span>{d.fileName}</span></div><div className="doc-meta"><span>{formatBytes(d.size)}</span><span>Application {d.applicationId.slice(-6)}</span></div>{d.remarks&&<div className="doc-remark"><MessageSquareText size={14}/>{d.remarks}</div>}<div className="document-card-actions"><button className="btn btn-outline btn-small" onClick={()=>openIntegrityFile(d.backendApplicationId,d.id)}><Eye size={14}/> Open file</button><button className="btn btn-outline btn-small" onClick={()=>{setSelectedId(d.applicationId);setPage('application-detail')}}><Eye size={14}/> View application</button>{isOfficer&&['Pending','Needs Review','Deficient'].includes(d.status)&&<button className="btn btn-primary btn-small" onClick={()=>{setReviewDoc({...d,backendApplicationId:d.backendApplicationId});setReviewRemark('')}}>Review</button>}{!isOfficer&&<button className="btn btn-outline btn-small" onClick={()=>{setUploadAppId(d.applicationId);setShowUpload(true)}}><Upload size={14}/> Add files</button>}</div></article>)}</div>{allDocs.length===0&&<div className="panel empty-state"><FileText size={32}/><h3>No documents yet</h3><p>Documents attached to your applications will appear here.</p></div>}</>}

        {page==='alerts'&&<><div className="page-heading"><div><div className="eyebrow">SERVICE-LEVEL MONITORING</div><h1>Alerts & deadlines</h1><p>Applications approaching or exceeding their target dates.</p></div></div><div className="alert-summary"><div><strong>{overdue}</strong><span>Overdue applications</span></div><div><strong>{mine.filter(a=>!['Approved','Rejected'].includes(a.status)&&a.deadline>=today()&&a.deadline<=addDays(7)).length}</strong><span>Due in 7 days</span></div><div><strong>{mine.filter(a=>a.status==='Deficient').length}</strong><span>Awaiting corrections</span></div></div><div className="panel table-panel"><div className="panel-heading"><div><h2>Attention required</h2><p>Open an application to see its history and take action.</p></div></div><ApplicationTable items={mine.filter(a=>!['Approved','Rejected'].includes(a.status)).sort((a,b)=>(a.deadline||'').localeCompare(b.deadline||''))} onOpen={a=>{setSelectedId(a.id);setPage('application-detail')}} empty="No active alerts. Great work!"/></div><PersistentAlertsPanel session={session} applications={mine} isOfficer={isOfficer} notify={notify}/></>}

        {page==='reports'&&<><div className="page-heading"><div><div className="eyebrow">PERFORMANCE & COMPLIANCE</div><h1>Reports</h1><p>Application distribution and current review workload.</p></div><button className="btn btn-primary" onClick={exportCsv}><Download size={16}/> Export CSV</button></div><div className="report-grid"><div className="panel report-panel"><h2>Application status</h2><p>Current status distribution</p>{[{s:'Pending',n:counts.pending,c:'bar-orange'},{s:'In Review',n:counts.review,c:'bar-navy'},{s:'Deficient',n:counts.deficient,c:'bar-red'},{s:'Approved',n:counts.approved,c:'bar-green'},{s:'Rejected',n:mine.filter(a=>a.status==='Rejected').length,c:'bar-rose'}].map(x=><div className="bar-row" key={x.s}><div><span>{x.s}</span><b>{x.n}</b></div><div className="bar-track"><i className={x.c} style={{width:`${counts.total?Math.max(x.n/counts.total*100,x.n?4:0):0}%`}}/></div></div>)}</div><div className="panel report-panel"><h2>Compliance snapshot</h2><p>Document-level verification</p>{[{label:'Documents submitted',n:allDocs.length},{label:'Documents approved',n:allDocs.filter(d=>d.status==='Approved').length},{label:'Documents pending',n:allDocs.filter(d=>d.status==='Pending').length},{label:'Documents deficient',n:allDocs.filter(d=>d.status==='Deficient').length}].map(x=><div className="snapshot-row" key={x.label}><span>{x.label}</span><strong>{x.n}</strong></div>)}</div></div><div className="panel report-note"><ShieldCheck size={20}/><div><strong>Reporting note</strong><p>Application counts below reflect the signed-in dashboard records. The live report panel loads additional database-backed EVC, compliance, expiry and regional workload aggregates from Flask.</p></div></div><LiveReportSummary isOfficer={isOfficer||isAuthority} notify={notify}/></>}

        {page==='operations'&&<OperationsWorkspace session={session} applications={mine} isOfficer={isOfficer} isCommittee={isCommittee} isAuthority={isAuthority} refreshApplications={refreshApplications} notify={notify}/>}

        {page==='application-detail'&&selected&&<><div className="detail-back"><button className="text-button" onClick={()=>setPage('applications')}>← Back to applications</button><span className="detail-id">{selected.id}</span></div><div className="page-heading detail-heading"><div><div className="eyebrow">APPLICATION RECORD</div><h1>{selected.institution}</h1><p>{selected.type} · {selected.state}</p></div><Status value={selected.status}/></div><div className="detail-layout"><div className="detail-main"><section className="panel detail-panel"><div className="panel-heading"><div><h2>Application information</h2><p>Submission details and current assignment</p></div><Building2 size={20} className="muted-icon"/></div><div className="detail-fields"><Info label="Application ID" value={selected.id}/><Info label="Institution" value={selected.institution}/><Info label="Application type" value={selected.type}/><Info label="State / UT" value={selected.state}/><Info label="Contact email" value={selected.contact}/><Info label="Submission date" value={fmtDate(selected.submittedAt)}/><Info label="Review deadline" value={fmtDate(selected.deadline)}/><Info label="Assigned officer" value={selected.officer}/><Info label="Current stage" value={selected.stage}/></div>{selected.remarks&&<div className="remarks-box"><MessageSquareText size={16}/><div><strong>Latest remarks</strong><p>{selected.remarks}</p></div></div>}</section><DocumentRequirementProgress application={selected}/><section className="panel detail-panel"><div className="panel-heading"><div><h2>Submitted documents</h2><p>{selected.documents.length} document(s) attached to this application</p></div>{!canSeeAll&&<button className="btn btn-outline btn-small" onClick={()=>{setUploadAppId(selected.id);setShowUpload(true)}}><Upload size={14}/> Add documents</button>}</div><div className="detail-doc-list">{selected.documents.map(d=><div className="detail-doc-row" key={d.id}><div className="file-icon"><FileText size={19}/></div><div className="detail-doc-info"><strong>{d.name}</strong><small>{d.fileName} · {formatBytes(d.size)}</small>{d.remarks&&<em>{d.remarks}</em>}</div><Status value={d.status}/>{canSeeAll&&<button className="btn btn-outline btn-small" onClick={()=>openIntegrityFile(selected.backendId,d.id)}>Open file</button>}{isOfficer&&['Pending','Needs Review','Deficient'].includes(d.status)&&<button className="btn btn-outline btn-small" onClick={()=>{setReviewDoc({...d,applicationId:selected.id,backendApplicationId:selected.backendId,institution:selected.institution});setReviewRemark('')}}>Review</button>}</div>)}{selected.documents.length===0&&<p className="muted-text">No documents attached yet.</p>}</div></section></div><aside className="detail-side"><section className="panel action-panel"><h2>{isOfficer?'Officer actions':'Application status'}</h2>{isOfficer?<><label className="field-label">Assign reviewing officer</label><select className="field-control" value={selected.officer} onChange={e=>updateApp(selected.id,{officer:e.target.value},decisionRemark.trim())}><option>Unassigned</option><option>Ananya Rao</option><option>Rahul Menon</option><option>Priya Sharma</option><option>Vikram Shah</option></select><label className="field-label">Workflow stage</label><select className="field-control" value={selected.stage} onChange={e=>{if(!decisionRemark.trim()){notify('Enter a reason in Review remarks before changing the workflow stage.');return;}updateApp(selected.id,{stage:e.target.value},decisionRemark.trim());}}>{[selected.stage,...({Submitted:['Initial Scrutiny','Scrutiny'], 'Initial Scrutiny':['Document Verification','Deficiency Raised'], 'Document Verification':['Technical Review','Deficiency Raised'], 'Deficiency Raised':[], 'Resubmitted':['Document Verification','Technical Review'], 'Technical Review':['Committee Review','Decision Pending'], 'Committee Review':['Decision Pending'], Scrutiny:['EVC','Decision Pending'], EVC:['SAC/SHC','Decision Pending'], 'SAC/SHC':['Decision Pending']}[selected.stage]||[])].filter((v,i,a)=>a.indexOf(v)===i).map(s=><option key={s}>{s}</option>)}</select><label className="field-label">Review remarks</label><textarea className="field-control textarea" placeholder="Add a note for the institution…" value={decisionRemark} onChange={e=>setDecisionRemark(e.target.value)}/><div className="action-buttons"><button className="btn btn-success" disabled={selected.stage!=='Decision Pending'} onClick={()=>decide(selected,'Approved',decisionRemark)}><Check size={16}/> Approve</button><button className="btn btn-danger" onClick={()=>decide(selected,'Deficient',decisionRemark)}><AlertTriangle size={16}/> Request correction</button><button className="btn btn-outline full-width" disabled={selected.stage!=='Decision Pending'} onClick={()=>decide(selected,'Rejected',decisionRemark)}><XCircle size={16}/> Reject application</button></div></>:isCommittee?<><div className="institution-status"><Status value={selected.status}/><p>This case is assigned to your EVC committee. Use EVC management to update the visit and completion status.</p></div><button className="btn btn-primary full-width" onClick={()=>setPage('operations')}>Open EVC management</button></>:isAuthority?<><div className="institution-status"><Status value={selected.status}/><p>Authority decision controls are available only after the case reaches Decision Pending.</p></div><label className="field-label">Decision remarks (required)</label><textarea className="field-control textarea" placeholder="Enter the reason for the final decision…" value={decisionRemark} onChange={e=>setDecisionRemark(e.target.value)}/><div className="action-buttons"><button className="btn btn-success" disabled={selected.stage!=='Decision Pending'} onClick={()=>decide(selected,'Approved',decisionRemark)}><Check size={16}/> Approve</button><button className="btn btn-danger" disabled={selected.stage!=='Decision Pending'} onClick={()=>decide(selected,'Rejected',decisionRemark)}><XCircle size={16}/> Reject</button></div></>:<><div className="institution-status"><Status value={selected.status}/><p>{selected.status==='Deficient'?'Action is required. Review the officer remarks and upload corrected documents.':selected.status==='Approved'?'Your application has been approved.':selected.status==='Rejected'?'A decision has been issued. Contact support if you need clarification.':'Your application is in the review workflow.'}</p></div><button className="btn btn-primary full-width" onClick={()=>{setUploadAppId(selected.id);setShowUpload(true)}}><Upload size={16}/> Upload / add documents</button>{selected.status==='Draft'&&<button className="btn btn-success full-width" onClick={()=>submitApplication(selected)}><Check size={16}/> Submit for review</button>}{selected.status==='Deficient'&&selected.stage==='Deficiency Raised'&&<button className="btn btn-success full-width" onClick={()=>submitApplication(selected)}><Check size={16}/> Resubmit corrected application</button>}</>}</section><section className="panel timeline-panel"><h2>Workflow timeline</h2>{[{label:'Application submitted',date:selected.submittedAt,done:true},{label:'Initial scrutiny',date:selected.submittedAt,done:true},{label:'Officer review',date:selected.status==='Approved'?selected.deadline:'In progress',done:['In Review','Approved','Deficient','Rejected'].includes(selected.status)},{label:'Decision issued',date:selected.status==='Approved'||selected.status==='Rejected'?today():'Pending',done:['Approved','Rejected'].includes(selected.status)}].map((t,i)=><div className={`timeline-item ${t.done?'done':''}`} key={t.label}><span className="timeline-dot">{t.done?<Check size={11}/>:null}</span><div><strong>{t.label}</strong><small>{t.date==='In progress'||t.date==='Pending'?t.date:fmtDate(t.date)}</small></div></div>)}</section></aside></div></>}

      </main>

      <footer className="footer"><span>© {new Date().getFullYear()} AICTEFlow · Approval & Compliance Workspace</span><span><ShieldCheck size={13}/> Demonstration interface</span></footer>

    </div>

    {mobileOpen&&<button className="mobile-scrim" onClick={()=>setMobileOpen(false)} aria-label="Close menu"/>}

    {showNew && session?.role==='institution' && <Modal title={isOfficer?'Register institution application':'Submit a new application'} onClose={()=>setShowNew(false)} wide><form onSubmit={createApplication} className="modal-body"><div className="form-intro"><span className="form-intro-icon"><GraduationCap size={22}/></span><div><strong>Institution application</strong><p>Create a draft first, upload the required documents, then submit it for review.</p></div></div><div className="form-grid"><div className="form-field span-2"><label>Institution / college name</label><input required value={form.institution} onChange={e=>setForm({...form,institution:e.target.value})} placeholder="Enter the registered institution name"/></div><div className="form-field"><label>Application type</label><select required value={form.type} onChange={e=>setForm({...form,type:e.target.value})}>{['New Institution','Extension of Approval','Increase in Intake','New Course','Change of Institution Name','Closure of Course'].map(x=><option key={x}>{x}</option>)}</select></div><div className="form-field"><label>State / UT</label><select value={form.state} onChange={e=>setForm({...form,state:e.target.value})}>{['Karnataka','Andhra Pradesh','Telangana','Tamil Nadu','Maharashtra','Kerala','Delhi','Gujarat','Rajasthan','Uttar Pradesh','Other'].map(x=><option key={x}>{x}</option>)}</select></div><div className="form-field"><label>Review deadline</label><p className="ops-muted">The review deadline is assigned by the AICTE workflow when your application is submitted successfully. Institutions cannot set or change it. An authorized AICTE officer may revise it with a recorded reason.</p></div>

<div className="form-field">

  <label>Institution contact email</label>

  <input

    type="email"

    required

    disabled={!isOfficer}

    value={isOfficer ? form.contact : session.email}

    onChange={e =>

      setForm({ ...form, contact: e.target.value })

    }

    placeholder="office@institution.edu.in"

  />

  {!isOfficer && (

    <small>

      This application is linked to your signed-in account.

    </small>

  )}

</div>



<div className="form-field span-2"><label>Additional notes</label><textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} placeholder="Optional details for the reviewing officer"/></div><div className="form-field span-2"><label>Attach initial documents</label><label className="dropzone"><Upload size={22}/><strong>Choose files to attach</strong><span>PDF, JPG or PNG</span><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setFiles(Array.from(e.target.files||[]))}/></label>{files.length>0&&<div className="chosen-files">{files.map(f=><span key={f.name}><FileText size={13}/>{f.name}<button type="button" onClick={()=>setFiles(p=>p.filter(x=>x.name!==f.name))}><X size={13}/></button></span>)}</div>}</div></div><div className="modal-footer"><button type="button" className="btn btn-outline" onClick={()=>setShowNew(false)}>Cancel</button><button type="submit" className="btn btn-primary"><Check size={16}/> Create draft</button></div></form></Modal>}

    {showUpload&&<Modal title="Upload application documents" onClose={()=>setShowUpload(false)}><form onSubmit={uploadDocuments} className="modal-body"><div className="form-field"><label>Application <b>\*</b></label><select required value={uploadAppId} onChange={e=>setUploadAppId(e.target.value)}><option value="">Choose application</option>{mine.map(a=><option key={a.id} value={a.id}>{a.id} · {a.institution}</option>)}</select></div><div className="form-field"><label>Select documents <b>\*</b></label><label className="dropzone"><Upload size={22}/><strong>Choose files to upload</strong><span>PDF, JPG or PNG</span><input type="file" multiple required accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setUploadFiles(Array.from(e.target.files||[]))}/></label>{uploadFiles.length>0&&<div className="chosen-files">{uploadFiles.map(f=><span key={f.name}><FileText size={13}/>{f.name}<button type="button" onClick={()=>setUploadFiles(p=>p.filter(x=>x.name!==f.name))}><X size={13}/></button></span>)}</div>}</div><div className="notice-box"><AlertTriangle size={16}/><p>Files are uploaded to the Flask server. Choose files in the same order as the document requirements; only PDF, JPG and PNG files are accepted.</p></div><div className="modal-footer"><button type="button" className="btn btn-outline" onClick={()=>setShowUpload(false)}>Cancel</button><button type="submit" className="btn btn-primary"><Upload size={16}/> Add documents</button></div></form></Modal>}

    {reviewDoc&&<Modal title="Review document" onClose={()=>setReviewDoc(null)}><div className="modal-body"><div className="review-document"><div className="file-icon"><FileText size={22}/></div><div><strong>{reviewDoc.name}</strong><p>{reviewDoc.fileName}</p><small>{reviewDoc.institution} · {reviewDoc.applicationId}</small></div></div><div className="notice-box"><AlertTriangle size={16}/><p>Open the original file and review any integrity flags before deciding. Screening signals are advisory and do not prove fraud.</p></div><div className="form-field"><label>Review remarks</label><textarea value={reviewRemark} onChange={e=>setReviewRemark(e.target.value)} placeholder="Add feedback for the institution…"/></div><div className="modal-footer review-actions"><button className="btn btn-outline" onClick={()=>openIntegrityFile(reviewDoc.backendApplicationId,reviewDoc.id)}><Eye size={15}/> Open original file</button><button className="btn btn-outline" onClick={()=>reviewDocument(reviewDoc.applicationId,reviewDoc.id,'Deficient',reviewRemark||'Please upload a valid document.') }><AlertTriangle size={15}/> Mark deficient</button><button className="btn btn-success" onClick={()=>reviewDocument(reviewDoc.applicationId,reviewDoc.id,'Approved',reviewRemark)}><Check size={16}/> Approve document</button></div></div></Modal>}

    {toast&&<div className="toast"><CheckCircle2 size={18}/>{toast}<button onClick={()=>setToast('')}><X size={15}/></button></div>}

  </div>;

}




function DocumentRequirementProgress({application}) {
  const [requirements,setRequirements]=useState([]);
  const [loadError,setLoadError]=useState('');
  useEffect(()=>{
    let active=true;
    if(!application?.backendId){setRequirements([]);return ()=>{active=false;};}
    backend(`/api/document-requirements?application_type=${encodeURIComponent(application.type)}`)
      .then(data=>{if(active){setRequirements(data.documents||[]);setLoadError('');}})
      .catch(err=>{if(active)setLoadError(err.message);});
    return ()=>{active=false;};
  },[application?.backendId,application?.type]);
  const latest=new Map();
  for(const doc of (application?.documents||[])){
    const previous=latest.get(Number(doc.requirementId));
    if(!previous||Number(doc.id)>Number(previous.id))latest.set(Number(doc.requirementId),doc);
  }
  const ordered=[...requirements].sort((a,b)=>a.sequence_order-b.sequence_order);
  const next=ordered.find(req=>req.is_mandatory&&!latest.has(Number(req.id)));
  return <section className="panel detail-panel"><div className="panel-heading"><div><h2>Document requirements checklist</h2><p>Required items and the next upload step for this application type.</p></div></div>{loadError&&<div className="notice-box"><AlertTriangle size={16}/><p>Requirements could not be loaded: {loadError}</p></div>}{!ordered.length&&!loadError&&<p className="muted-text">Loading requirements…</p>}<div className="ops-list">{ordered.map(req=>{const doc=latest.get(Number(req.id));const status=!doc?'Missing':doc.status==='Superseded'?'Missing':doc.rawStatus||doc.status;return <article className="ops-row" key={req.id}><div className="ops-row-main"><strong>{req.sequence_order}. {req.document_name}{req.is_mandatory?' *':''}</strong><small>{req.description||'Requirement configured for this demo application type.'}</small><p>{doc?`Uploaded file: ${doc.fileName} · Status: ${status}`:'Not uploaded yet'}</p></div><Status value={doc?(doc.status==='Approved'?'Approved':doc.status==='Deficient'?'Deficient':doc.status==='Needs Review'?'Needs Review':'Pending'):'Pending'}/></article>;})}{ordered.length>0&&<article className="ops-row"><div className="ops-row-main"><strong>Next required upload</strong><p>{next?.document_name||'All configured required documents have been uploaded. Resolve verification flags before submission.'}</p></div></article>}</div><p className="ops-muted">The displayed document requirements are configurable demo placeholders and must be checked against authoritative application rules before real use.</p></section>;
}

function PersistentAlertsPanel({session,applications,isOfficer,notify}) {
  const [alerts,setAlerts]=useState([]);
  const [loading,setLoading]=useState(false);
  const [sending,setSending]=useState(false);
  const [error,setError]=useState('');
  const load=async()=>{
    setLoading(true);setError('');
    try{const data=await backend('/api/alerts/records');setAlerts(data.alerts||[]);}
    catch(err){setError(err.message);}
    finally{setLoading(false);}
  };
  useEffect(()=>{load();},[session?.email,session?.role]);
  const act=async(alert,action)=>{
    try{await backend(`/api/alerts/records/${alert.id}`,{method:'PUT',body:JSON.stringify({action})});await load();notify(`Alert ${{acknowledge:'acknowledged',close:'closed',reopen:'reopened'}[action]} successfully.`);}
    catch(err){notify(`Could not update alert: ${err.message}`);}
  };
  const sendDigest=async()=>{
    setSending(true);
    try{const result=await backend('/api/alerts/email-digest',{method:'POST',body:JSON.stringify({})});notify(`Email digest processed: ${result.sent||0} sent, ${result.failed||0} failed.`);await load();}
    catch(err){notify(err.message);}
    finally{setSending(false);}
  };
  return <section className="panel ops-section">
    <div className="panel-heading"><div><h2>Persistent alert centre</h2><p>Database-backed alerts with acknowledgement, closure and audit records.</p></div><div className="ops-actions"><button className="btn btn-outline btn-small" onClick={load} disabled={loading}>Refresh</button>{isOfficer&&<button className="btn btn-primary btn-small" onClick={sendDigest} disabled={sending}>{sending?'Sending…':'Send email digest'}</button>}</div></div>
    {error&&<div className="notice-box"><AlertTriangle size={16}/><p>{error}</p></div>}
    <div className="ops-list">{alerts.map(a=><article className="ops-alert-row" key={a.id}><div className="ops-alert-symbol"><Bell size={17}/></div><div className="ops-row-main"><strong>{a.title}</strong><p>{a.details||a.type}</p><small>{a.due_at?`Due ${fmtDate(a.due_at.slice(0,10))} · `:''}{a.status}{a.acknowledged_by?` · acknowledged by ${a.acknowledged_by}`:''}{a.escalation_level?` · Escalation level ${a.escalation_level}`:''}{a.escalated_to?.length?` · Assigned: ${a.escalated_to.join(', ')}`:''}</small></div><div className="ops-actions">{session?.role==='institution'&&a.status==='Open'&&<button className="btn btn-outline btn-small" onClick={()=>act(a,'acknowledge')}>Acknowledge</button>}{isOfficer&&a.status!=='Closed'&&<button className="btn btn-outline btn-small" onClick={()=>act(a,'escalate')}>Escalate</button>}{(isOfficer||session?.role==='authority')&&a.status!=='Closed'&&<button className="btn btn-outline btn-small" onClick={()=>act(a,'close')}>Close</button>}{(isOfficer||session?.role==='authority')&&a.status==='Closed'&&<button className="btn btn-outline btn-small" onClick={()=>act(a,'reopen')}>Reopen</button>}</div></article>)}{!loading&&!alerts.length&&<div className="ops-empty">No persistent alerts are open or recorded yet. Deadline, expiry and overdue records are checked when this panel refreshes.</div>}</div>
    {isOfficer&&<p className="ops-muted">Email delivery is optional and requires SMTP settings in .env. Run send_scheduled_alerts.py from Windows Task Scheduler for recurring escalation/email checks.</p>}
  </section>;
}

function LiveReportSummary({isOfficer,notify}) {
  const [data,setData]=useState(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  const load=async()=>{setLoading(true);setError('');try{setData(await backend('/api/reports/summary'));}catch(err){setError(err.message);}finally{setLoading(false);}};
  useEffect(()=>{load();},[]);
  if(!isOfficer)return null;
  const pairs=(obj)=>Object.entries(obj||{}).sort((a,b)=>Number(b[1]||0)-Number(a[1]||0));
  const exportReport=()=>{
    if(!data){notify('Load the live report before exporting.');return;}
    const rows=[['Section','Metric','Value'],['Generated','At',data.generated_at||'']];
    const flatten=(section,obj)=>Object.entries(obj||{}).forEach(([k,v])=>rows.push([section,k,typeof v==='object'&&v!==null?JSON.stringify(v):v]));
    flatten('Applications',data.applications);flatten('Documents',data.documents);flatten('EVC',data.evc);flatten('Compliance',data.undertakings);flatten('Officer workload',data.officer_workload);flatten('Regional workload',data.regional_workload);flatten('Institution workload',data.institution_workload);flatten('Committee workload',data.committee_workload);
    const csv=rows.map(row=>row.map(value=>`"${String(value??'').replace(/"/g,'""')}"`).join(',')).join('\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='aicte-consolidated-workflow-report.csv';a.click();URL.revokeObjectURL(url);
  };
  return <section className="panel ops-section"><div className="panel-heading"><div><h2>Live workflow and compliance report</h2><p>Aggregates loaded from database records, not local demo cards.</p></div><div className="ops-actions"><button className="btn btn-outline btn-small" onClick={load} disabled={loading}>Refresh report</button><button className="btn btn-primary btn-small" onClick={exportReport} disabled={!data}>Download consolidated CSV</button></div></div>
    {error&&<div className="notice-box"><AlertTriangle size={16}/><p>Report could not load: {error}</p></div>}
    {loading&&!data?<div className="ops-empty">Loading report data…</div>:data&&<><div className="ops-summary-grid">{[{label:'Total applications',value:data.applications?.total||0},{label:'Active applications',value:data.applications?.active||0},{label:'Overdue applications',value:data.applications?.overdue||0},{label:'Expired documents',value:data.documents?.expired||0},{label:`Expiring within ${data.documents?.expiry_warning_days||30} days`,value:data.documents?.expiring_within_warning_window??data.documents?.expiring_within_30_days??0},{label:'Renewals pending',value:data.documents?.renewals_pending_verification||0},{label:'Overdue EVC',value:data.evc?.overdue||0},{label:'Overdue compliance',value:data.undertakings?.overdue||0}].map(x=><div className="ops-summary-card" key={x.label}><span>{x.label}</span><strong>{x.value}</strong></div>)}</div>
    <div className="ops-report-columns"><div><h3>Applications by status</h3>{pairs(data.applications?.by_status).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Applications by stage</h3>{pairs(data.applications?.by_stage).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Regional workload</h3>{pairs(data.regional_workload).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Officer workload</h3>{pairs(data.officer_workload).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Committee workload</h3>{pairs(data.committee_workload).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Institution workload</h3>{pairs(data.institution_workload).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Application age</h3>{pairs(data.applications?.aging_buckets).map(([k,v])=><div className="snapshot-row" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div><h3>Status by region</h3>{Object.entries(data.applications?.status_by_region||{}).map(([region,statuses])=><div className="snapshot-row" key={region}><span>{region}</span><strong>{Object.entries(statuses||{}).map(([s,n])=>`${s}: ${n}`).join(' · ')||'—'}</strong></div>)}</div><div><h3>Status by institution</h3>{Object.entries(data.applications?.status_by_institution||{}).map(([institution,statuses])=><div className="snapshot-row" key={institution}><span>{institution}</span><strong>{Object.entries(statuses||{}).map(([s,n])=>`${s}: ${n}`).join(' · ')||'—'}</strong></div>)}</div></div><p className="ops-muted">Generated {data.generated_at?new Date(data.generated_at).toLocaleString():''}. The report only includes persisted records that have been entered; it does not infer official regulatory compliance.</p></>}
  </section>;
}

function OperationsWorkspace({session,applications,isOfficer,isCommittee,isAuthority,refreshApplications,notify}) {
  const [selectedId,setSelectedId]=useState('');
  const [evcs,setEvcs]=useState([]);const [undertakings,setUndertakings]=useState([]);const [documents,setDocuments]=useState([]);const [communications,setCommunications]=useState([]);const [history,setHistory]=useState([]);const [caseSummary,setCaseSummary]=useState('');
  const [expiryAlerts,setExpiryAlerts]=useState([]);const [overdueEvc,setOverdueEvc]=useState([]);const [overdueCompliance,setOverdueCompliance]=useState([]);const [rules,setRules]=useState([]);
  const [loading,setLoading]=useState(false);const [error,setError]=useState('');const [saving,setSaving]=useState(false);
  const [evcForm,setEvcForm]=useState({scheduled_date:'',committee_name:'EVC Committee',assigned_officer:'',remarks:''});
  const [undertakingForm,setUndertakingForm]=useState({title:'',description:'',due_date:''});
  const [communicationForm,setCommunicationForm]=useState({template_key:'deficiency_notice',subject:'',body:''});
  const [validityForm,setValidityForm]=useState({});const [renewalForm,setRenewalForm]=useState({});
  const [editForm,setEditForm]=useState({state:'',deadline:'',reason:''});
  const [summaryExpanded,setSummaryExpanded]=useState(false);
  const selected=applications.find(a=>String(a.backendId)===String(selectedId))||null;
  const canManage=Boolean(isOfficer);
  const fmtDateTime=(v)=>v?new Date(v).toLocaleString():'Not scheduled';
  useEffect(()=>{if(!selectedId&&applications.length)setSelectedId(String(applications[0].backendId||''));},[applications,selectedId]);
  const load=async()=>{
    setError('');setLoading(true);
    try{
      const work=[];
      if(selected?.backendId){
        work.push(backend(`/api/applications/${selected.backendId}/evc`).then(d=>setEvcs(d.evc_records||[])));
        work.push(backend(`/api/applications/${selected.backendId}/undertakings`).then(d=>setUndertakings(d.undertakings||[])));
        work.push(backend(`/api/applications/${selected.backendId}/documents`).then(d=>{setDocuments(d.documents||[]);setValidityForm(Object.fromEntries((d.documents||[]).map(x=>[x.id,{issue_date:x.issue_date||'',expiry_date:x.expiry_date||'',reason:''}])));setRenewalForm(Object.fromEntries((d.documents||[]).map(x=>[x.id,{issue_date:'',expiry_date:'',remarks:'',file:null}])));}));
        work.push(backend(`/api/applications/${selected.backendId}/communications`).then(d=>setCommunications(d.communications||[])));
        work.push(backend(`/api/applications/${selected.backendId}/history`).then(d=>setHistory(d.history||d.audit_log||d.events||[])));
        work.push(backend(`/api/applications/${selected.backendId}/case-summary`).then(d=>setCaseSummary(d.summary||'')));
      } else {setEvcs([]);setUndertakings([]);setDocuments([]);setCommunications([]);setHistory([]);setCaseSummary('');}
      if(isOfficer){
        work.push(backend('/api/documents/expiry-alerts').then(d=>setExpiryAlerts(d.alerts||[])));
        work.push(backend('/api/evc/overdue').then(d=>setOverdueEvc(d.overdue_evc||[])));
        work.push(backend('/api/undertakings/overdue').then(d=>setOverdueCompliance(d.overdue_undertakings||[])));
        work.push(backend('/api/regulatory-rules').then(d=>setRules(d.rules||[])));
      } else {setExpiryAlerts([]);setOverdueEvc([]);setOverdueCompliance([]);setRules([]);}
      const results=await Promise.allSettled(work);const first=results.find(r=>r.status==='rejected');if(first)setError(first.reason?.message||'Some records could not load.');
    }catch(err){setError(err.message);}
    finally{setLoading(false);}
  };
  useEffect(()=>{if(selected?.backendId)load();},[selected?.backendId,session?.role]);
  const saveAction=async(label,fn)=>{setSaving(true);try{await fn();await load();if(refreshApplications)await refreshApplications();notify(`${label} saved successfully.`);}catch(err){notify(`${label} failed: ${err.message}`);}finally{setSaving(false);}};
  const scheduleEvc=()=>saveAction('EVC schedule',async()=>{
    if(!selected?.backendId)throw new Error('Choose an application first');if(!evcForm.scheduled_date||!evcForm.committee_name.trim()||!evcForm.assigned_officer.trim())throw new Error('Scheduled date, committee name and a registered committee account email are required');
    await backend(`/api/applications/${selected.backendId}/evc`,{method:'POST',body:JSON.stringify({...evcForm,scheduled_date:evcForm.scheduled_date.length===16?`${evcForm.scheduled_date}:00`:evcForm.scheduled_date})});setEvcForm({scheduled_date:'',committee_name:'EVC Committee',assigned_officer:'',remarks:''});
  });
  const updateEvc=(record,status)=>saveAction(`EVC ${status.toLowerCase()}`,async()=>backend(`/api/applications/${selected.backendId}/evc/${record.id}`,{method:'PUT',body:JSON.stringify({status,remarks:record.remarks||`Updated by ${session.email}`})}));
  const createUndertaking=()=>saveAction('Compliance condition',async()=>{
    if(!undertakingForm.title.trim()||!undertakingForm.due_date)throw new Error('Condition title and due date are required');
    await backend(`/api/applications/${selected.backendId}/undertakings`,{method:'POST',body:JSON.stringify({...undertakingForm,due_date:undertakingForm.due_date.length===16?`${undertakingForm.due_date}:00`:undertakingForm.due_date})});setUndertakingForm({title:'',description:'',due_date:''});
  });
  const uploadEvidence=(item,file)=>saveAction('Compliance evidence upload',async()=>{
    if(!file)throw new Error('Choose an evidence file first');const body=new FormData();body.append('file',file);body.append('remarks','Evidence submitted through the compliance workspace.');
    await backend(`/api/applications/${selected.backendId}/undertakings/${item.id}/evidence`,{method:'POST',body});
  });
  const verifyUndertaking=(item,decision)=>{
    const remarks=window.prompt(decision==='Rejected'?'Reason for rejecting the evidence:':'Optional verification remarks:',decision==='Verified'?'Evidence reviewed and accepted.':'');
    if(remarks===null)return;if(decision==='Rejected'&&!remarks.trim()){notify('A rejection reason is required.');return;}
    return saveAction(`Compliance evidence ${decision.toLowerCase()}`,async()=>backend(`/api/applications/${selected.backendId}/undertakings/${item.id}/verify`,{method:'PUT',body:JSON.stringify({decision,performed_by:session.email,remarks})}));
  };
  const saveValidity=(doc)=>saveAction('Document validity dates',async()=>{
    const form=validityForm[doc.id]||{};if(!form.reason?.trim())throw new Error('A reason is mandatory for date changes');
    await backend(`/api/applications/${selected.backendId}/documents/${doc.id}/validity`,{method:'PUT',body:JSON.stringify(form)});
  });
  const uploadRenewal=(doc)=>saveAction('Document renewal upload',async()=>{
    const form=renewalForm[doc.id]||{};if(!form.file||!form.expiry_date)throw new Error('Choose a renewal file and expiry date');
    const body=new FormData();body.append('file',form.file);body.append('issue_date',form.issue_date||'');body.append('expiry_date',form.expiry_date);body.append('remarks',form.remarks||'Renewal uploaded for verification.');
    await backend(`/api/applications/${selected.backendId}/documents/${doc.id}/renew-upload`,{method:'POST',body});
  });
  const verifyRenewal=(doc,decision)=>{
    const remarks=window.prompt(decision==='Rejected'?'Reason for rejecting the renewal:':'Optional renewal verification remarks:',decision==='Verified'?'Renewal document verified.':'');if(remarks===null)return;if(decision==='Rejected'&&!remarks.trim()){notify('A rejection reason is required.');return;}
    return saveAction(`Renewal ${decision.toLowerCase()}`,async()=>backend(`/api/applications/${selected.backendId}/documents/${doc.id}/renew/verify`,{method:'PUT',body:JSON.stringify({decision,performed_by:session.email,remarks})}));
  };
  const sendCommunication=()=>saveAction('Case communication',async()=>{
    if(!communicationForm.body.trim())throw new Error('Enter the communication text');
    await backend(`/api/applications/${selected.backendId}/communications`,{method:'POST',body:JSON.stringify(communicationForm)});setCommunicationForm({template_key:'deficiency_notice',subject:'',body:''});
  });
  const saveRule=(rule,value)=>saveAction('Regulatory demo rule',async()=>backend('/api/regulatory-rules',{method:'PUT',body:JSON.stringify({key:rule.key,value})}));
  const updateApplicationMeta=()=>saveAction('Application metadata',async()=>{
    if(!editForm.reason.trim())throw new Error('A reason is required for application edits');
    const payload={reason:editForm.reason};if(editForm.state)payload.state=editForm.state;if(editForm.deadline)payload.deadline=editForm.deadline;
    await backend(`/api/applications/${selected.backendId}/edit`,{method:'PUT',body:JSON.stringify(payload)});setEditForm({state:'',deadline:'',reason:''});
  });
  const downloadSummary=()=>{if(!caseSummary){notify('No case summary loaded yet.');return;}const url=URL.createObjectURL(new Blob([caseSummary],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`${selected?.id||'case'}-summary.txt`;a.click();URL.revokeObjectURL(url);};
  return <div className="ops-workspace">
    <div className="page-heading"><div><div className="eyebrow">CASE OPERATIONS</div><h1>EVC, compliance and case communication</h1><p>Persistent operational records connected to the Flask database. Demo regulatory settings are not official AICTE rules.</p></div><button className="btn btn-outline" onClick={load} disabled={loading}>{loading?'Refreshing…':'Refresh records'}</button></div>
    {error&&<div className="notice-box"><AlertTriangle size={16}/><p>{error}</p></div>}
    <section className="panel ops-section"><div className="panel-heading"><div><h2>Select application</h2><p>Choose a saved application to manage its operational records.</p></div></div><div className="ops-content"><div className="form-field"><label>Application</label><select className="field-control" value={selectedId} onChange={e=>setSelectedId(e.target.value)}><option value="">Choose application</option>{applications.filter(a=>a.backendId).map(a=><option key={a.backendId} value={String(a.backendId)}>{a.id} · {a.institution} · {a.status}</option>)}</select></div>{selected&&<div className="ops-case-header"><strong>{selected.institution}</strong><span>{selected.type} · {selected.state} · {selected.stage}</span><button className="btn btn-outline btn-small" onClick={downloadSummary}>Download case summary</button></div>}</div></section>
    {!selected&&<div className="panel ops-empty">Create or select a saved application to use the EVC and compliance workspace.</div>}
    {selected&&<>
      <div className="ops-section-grid">
        <section className="panel ops-section"><div className="panel-heading"><div><h2>EVC management</h2><p>Schedule a visit and track committee completion.</p></div><ClipboardCheck size={19}/></div><div className="ops-content">{canManage&&<div className="ops-form-grid"><div className="form-field"><label>Scheduled date and time</label><input type="datetime-local" value={evcForm.scheduled_date} onChange={e=>setEvcForm({...evcForm,scheduled_date:e.target.value})}/></div><div className="form-field"><label>Committee name</label><input value={evcForm.committee_name} onChange={e=>setEvcForm({...evcForm,committee_name:e.target.value})}/></div><div className="form-field"><label>Assigned committee login email (required)</label><input type="email" required value={evcForm.assigned_officer} onChange={e=>setEvcForm({...evcForm,assigned_officer:e.target.value})} placeholder="committee@aicte.gov.in"/><small>Create the account first with <code>python create_user.py committee</code>.</small></div><div className="form-field"><label>Schedule remarks</label><input value={evcForm.remarks} onChange={e=>setEvcForm({...evcForm,remarks:e.target.value})}/></div><button className="btn btn-primary" onClick={scheduleEvc} disabled={saving}>Schedule EVC / route to queue</button></div>}
          <div className="ops-list">{evcs.map(e=><article className="ops-row" key={e.id}><div className="ops-row-main"><strong>{e.committee_name||'EVC Committee'}</strong><small>{fmtDateTime(e.scheduled_date)} · {e.status}</small><p>{e.remarks||''}</p></div>{(canManage||isCommittee)&&e.status!=='Completed'&&e.status!=='Cancelled'&&<div className="ops-actions">{isCommittee&&<button className="btn btn-success btn-small" onClick={()=>updateEvc(e,'Completed')} disabled={saving}>Mark completed</button>}{canManage&&<button className="btn btn-outline btn-small" onClick={()=>updateEvc(e,'In Progress')} disabled={saving}>In progress</button>}{canManage&&<button className="btn btn-success btn-small" onClick={()=>updateEvc(e,'Completed')} disabled={saving}>Complete</button>}</div>}</article>)}{!evcs.length&&<p className="ops-muted">No EVC records are scheduled for this application.</p>}</div>
          {isOfficer&&overdueEvc.length>0&&<div className="notice-box"><AlertTriangle size={16}/><p>{overdueEvc.length} EVC event(s) are overdue across the workload.</p></div>}
        </div></section>
        <section className="panel ops-section"><div className="panel-heading"><div><h2>Undertakings & compliance</h2><p>Record conditions, submit evidence and verify compliance.</p></div><ShieldCheck size={19}/></div><div className="ops-content">{canManage&&<div className="ops-form-grid"><div className="form-field"><label>Condition / undertaking</label><input value={undertakingForm.title} onChange={e=>setUndertakingForm({...undertakingForm,title:e.target.value})} placeholder="e.g. Submit updated safety certificate"/></div><div className="form-field"><label>Due date</label><input type="datetime-local" value={undertakingForm.due_date} onChange={e=>setUndertakingForm({...undertakingForm,due_date:e.target.value})}/></div><div className="form-field ops-full"><label>Description / evidence required</label><textarea value={undertakingForm.description} onChange={e=>setUndertakingForm({...undertakingForm,description:e.target.value})}/></div><button className="btn btn-primary" onClick={createUndertaking} disabled={saving}>Add compliance condition</button></div>}
          <div className="ops-list">{undertakings.map(u=><article className="ops-row" key={u.id}><div className="ops-row-main"><strong>{u.title}</strong><small>Due {fmtDateTime(u.due_date)} · {u.status}</small><p>{u.description||u.remarks||'No additional details'}</p>{u.evidence_file&&<small>Evidence received</small>}</div><div className="ops-actions">{session.role==='institution'&&!['Verified','Rejected'].includes(u.status)&&<label className="btn btn-outline btn-small ops-upload">Upload evidence<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={e=>e.target.files?.[0]&&uploadEvidence(u,e.target.files[0])}/></label>}{canManage&&u.status==='Submitted'&&<><button className="btn btn-success btn-small" onClick={()=>verifyUndertaking(u,'Verified')} disabled={saving}>Verify</button><button className="btn btn-danger btn-small" onClick={()=>verifyUndertaking(u,'Rejected')} disabled={saving}>Reject</button></>}</div></article>)}{!undertakings.length&&<p className="ops-muted">No compliance conditions have been entered for this application.</p>}</div>
          {isOfficer&&overdueCompliance.length>0&&<div className="notice-box"><AlertTriangle size={16}/><p>{overdueCompliance.length} compliance condition(s) are overdue across the workload.</p></div>}
        </div></section>
      </div>
      <section className="panel ops-section"><div className="panel-heading"><div><h2>Document validity and renewals</h2><p>Set issue/expiry dates, submit a renewal file and review it. Date edits require a reason.</p></div></div><div className="ops-list">{documents.map(d=>{const vf=validityForm[d.id]||{issue_date:'',expiry_date:'',reason:''};const rf=renewalForm[d.id]||{issue_date:'',expiry_date:'',remarks:'',file:null};return <article className="ops-doc-row" key={d.id}><div className="ops-row-main"><strong>{d.document_name||d.file_name}</strong><small>{d.file_name} · {d.upload_status} · Expires {d.expiry_date||'not recorded'} · Renewal: {d.renewal_status||'Not Required'}</small><p>{d.remarks||''}</p></div>{canManage&&<div className="ops-validity"><div className="ops-form-grid"><div className="form-field"><label>Issue date</label><input type="date" value={vf.issue_date} onChange={e=>setValidityForm({...validityForm,[d.id]:{...vf,issue_date:e.target.value}})}/></div><div className="form-field"><label>Expiry date</label><input type="date" value={vf.expiry_date} onChange={e=>setValidityForm({...validityForm,[d.id]:{...vf,expiry_date:e.target.value}})}/></div><div className="form-field ops-full"><label>Reason for date change (required)</label><input value={vf.reason} onChange={e=>setValidityForm({...validityForm,[d.id]:{...vf,reason:e.target.value}})}/></div><button className="btn btn-outline btn-small" onClick={()=>saveValidity(d)} disabled={saving}>Save validity</button></div></div>}{session.role==='institution'&&<div className="ops-validity"><div className="ops-form-grid"><div className="form-field"><label>Renewal file</label><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={e=>setRenewalForm({...renewalForm,[d.id]:{...rf,file:e.target.files?.[0]||null}})}/></div><div className="form-field"><label>New issue date</label><input type="date" value={rf.issue_date} onChange={e=>setRenewalForm({...renewalForm,[d.id]:{...rf,issue_date:e.target.value}})}/></div><div className="form-field"><label>New expiry date</label><input type="date" value={rf.expiry_date} onChange={e=>setRenewalForm({...renewalForm,[d.id]:{...rf,expiry_date:e.target.value}})}/></div><button className="btn btn-primary btn-small" onClick={()=>uploadRenewal(d)} disabled={saving}>Submit renewal</button></div></div>}{canManage&&d.renewal_status==='Submitted'&&<div className="ops-actions"><button className="btn btn-success btn-small" onClick={()=>verifyRenewal(d,'Verified')} disabled={saving}>Verify renewal</button><button className="btn btn-danger btn-small" onClick={()=>verifyRenewal(d,'Rejected')} disabled={saving}>Reject renewal</button></div>}</article>})}{!documents.length&&<div className="ops-empty">No uploaded documents are attached to this application yet.</div>}</div>{isOfficer&&expiryAlerts.length>0&&<div className="notice-box"><AlertTriangle size={16}/><p>{expiryAlerts.length} documents are expired or within the configured expiry warning window.</p></div>}</section>
      <div className="ops-section-grid"><section className="panel ops-section"><div className="panel-heading"><div><h2>Standardized communication</h2><p>Save a case message and generate a persistent audit event; email is sent only when SMTP is configured.</p></div><MessageSquareText size={18}/></div><div className="ops-content">{(isOfficer||session.role==='institution')&&<div className="ops-form-grid"><div className="form-field"><label>Message template</label><select value={communicationForm.template_key} onChange={e=>setCommunicationForm({...communicationForm,template_key:e.target.value})}>{[['deficiency_notice','Deficiency notice'],['correction_update','Correction update'],['approval_notice','Approval notice'],['evc_notice','EVC notice'],['compliance_reminder','Compliance reminder'],['general','General case communication']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div><div className="form-field"><label>Subject (optional)</label><input value={communicationForm.subject} onChange={e=>setCommunicationForm({...communicationForm,subject:e.target.value})}/></div><div className="form-field ops-full"><label>Message</label><textarea value={communicationForm.body} onChange={e=>setCommunicationForm({...communicationForm,body:e.target.value})} placeholder="Explain the requested action, supporting evidence and target date…"/></div><button className="btn btn-primary" onClick={sendCommunication} disabled={saving}>Save / send message</button></div>}<div className="ops-list">{communications.map(c=><article className="ops-row" key={c.id}><div className="ops-row-main"><strong>{c.subject}</strong><small>{c.template_key} · {c.sender_email} · {c.delivery_status} · {fmtDateTime(c.created_at)}</small><p>{c.body}</p></div></article>)}{!communications.length&&<p className="ops-muted">No case communications yet.</p>}</div></div></section>
      <section className="panel ops-section"><div className="panel-heading"><div><h2>Case history and summary</h2><p>Download a readable case summary including documents, integrity flags, compliance, EVC and audit events.</p></div><Download size={18}/></div><div className="ops-content"><button className="btn btn-outline btn-small" onClick={downloadSummary}>Download case summary (.txt)</button><button className="btn btn-outline btn-small" onClick={()=>setSummaryExpanded(v=>!v)}>{summaryExpanded?'Hide case summary':'Preview case summary'}</button>{summaryExpanded&&<pre className="ops-summary-text">{caseSummary||'No summary loaded yet.'}</pre>}<div className="ops-list">{history.slice(0,15).map((h,i)=><article className="ops-row" key={h.id||i}><div className="ops-row-main"><strong>{h.action||h.stage_name||'Workflow event'}</strong><small>{h.timestamp||h.created_at||h.started_at||''} · {h.performed_by||h.assigned_to||''}</small><p>{h.details||h.remarks||h.status||''}</p></div></article>)}{!history.length&&<p className="ops-muted">No history records were returned for this case.</p>}</div></div></section></div>
      {canManage&&<section className="panel ops-section"><div className="panel-heading"><div><h2>Application edits with reason</h2><p>Changing state or deadline requires a reason and creates an audit record.</p></div></div><div className="ops-content"><div className="ops-form-grid"><div className="form-field"><label>Region / state</label><select value={editForm.state} onChange={e=>setEditForm({...editForm,state:e.target.value})}><option value="">Keep current state</option>{['Karnataka','Andhra Pradesh','Telangana','Tamil Nadu','Maharashtra','Kerala','Delhi','Gujarat','Rajasthan','Uttar Pradesh','Other'].map(x=><option key={x}>{x}</option>)}</select></div><div className="form-field"><label>Review deadline</label><input type="date" value={editForm.deadline} onChange={e=>setEditForm({...editForm,deadline:e.target.value})}/></div><div className="form-field ops-full"><label>Mandatory change reason</label><input value={editForm.reason} onChange={e=>setEditForm({...editForm,reason:e.target.value})}/></div><button className="btn btn-primary" onClick={updateApplicationMeta} disabled={saving}>Save application edits</button></div></div></section>}
      {canManage&&<RegulatoryRulesPanel rules={rules} saveRule={saveRule} saving={saving}/>}
    </>}
  </div>;
}

function RegulatoryRulesPanel({rules,saveRule,saving}){
  const labels={duplicate_text_similarity:'Near-duplicate text similarity threshold',expiry_warning_days:'Expiry warning window (days)',escalation_level_1_days:'Escalation level 1 after overdue days',escalation_level_2_days:'Escalation level 2 after overdue days',manual_review_all_integrity_flags:'Send all integrity flags to manual review',email_alerts_enabled:'Allow configured email notifications'};
  return <section className="panel ops-section"><div className="panel-heading"><div><h2>Configurable demonstration rules</h2><p>These settings are illustrative and are not official AICTE or APH rules.</p></div><Settings size={18}/></div><div className="ops-content"><div className="ops-rules-grid">{rules.map(r=><RuleEditor key={r.key} rule={r} label={labels[r.key]||r.label} onSave={saveRule} saving={saving}/>)}</div>{!rules.length&&<p className="ops-muted">No rule rows are seeded. Run the backend and the local rule seeding routine to create defaults.</p>}</div></section>;
}
function RuleEditor({rule,label,onSave,saving}){
  const [value,setValue]=useState(rule.value||'');useEffect(()=>setValue(rule.value||''),[rule.value]);
  return <div className="ops-rule"><label>{label}</label><p>{rule.description||'Local demonstration setting'}</p><div className="ops-rule-edit"><input value={value} onChange={e=>setValue(e.target.value)} type={['expiry_warning_days','escalation_level_1_days','escalation_level_2_days'].includes(rule.key)?'number':(['manual_review_all_integrity_flags','email_alerts_enabled'].includes(rule.key)?'text':'number')} min={rule.key==='duplicate_text_similarity'?0.5:1} max={rule.key==='duplicate_text_similarity'?0.99:730} step={rule.key==='duplicate_text_similarity'?0.01:1}/><button className="btn btn-outline btn-small" onClick={()=>onSave(rule,value)} disabled={saving}>Save</button></div></div>;
}


function Info({label,value}){return <div className="info-field"><span>{label}</span><strong>{value||'—'}</strong></div>}

function ApplicationTable({items,onOpen,compact=false,empty}){return <div className={`table-wrap ${compact?'compact-table':''}`}>{items.length===0?<div className="empty-state"><FileText size={29}/><p>{empty||'No applications found.'}</p></div>:<table><thead><tr><th>Institution / Application</th><th>Type</th><th>Submitted</th><th>Deadline</th><th>Status</th><th></th></tr></thead><tbody>{items.map(a=><tr key={a.id} onClick={()=>onOpen(a)}><td><div className="institution-cell"><span className="institution-avatar"><Building2 size={17}/></span><span><strong>{a.institution}</strong><small>{a.id}</small></span></div></td><td><span className="type-cell">{a.type}</span></td><td>{fmtDate(a.submittedAt)}</td><td><span className={a.deadline<today()&&!['Approved','Rejected'].includes(a.status)?'overdue-date':''}>{fmtDate(a.deadline)}</span></td><td><Status value={a.status}/></td><td><button className="row-open" aria-label={`Open ${a.id}`}><ArrowRight size={16}/></button></td></tr>)}</tbody></table>}</div>}



function Login({onLogin}){const [role,setRole]=useState('institution');const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [error,setError]=useState('');const [mode,setMode]=useState('login');const [institutionName,setInstitutionName]=useState('');async function submit(e){e.preventDefault();if(!email.trim()||!password.trim()){setError('Enter an email and password to continue.');return;}if(!/^\S+@\S+\.\S+$/.test(email)){setError('Enter a valid email address.');return;}setError('');if(mode==='register'&&!institutionName.trim()){setError('Enter your institution name.');return;}const result=await onLogin(role,email.trim(),password,mode,institutionName.trim());if(result&&result.error)setError(result.error);}return <div className="login-page"><div className="login-left"><div className="login-brand"><Brand/></div><div className="login-hero"><div className="eyebrow light-eyebrow">DIGITAL APPROVAL WORKFLOW</div><h1>From application to approval.<br/><span>Clear at every step.</span></h1><p>A unified workspace for institutions and AICTE officers to manage applications, documents, compliance and review timelines.</p><div className="login-feature-list"><div><span><Check size={15}/></span> Transparent application tracking</div><div><span><Check size={15}/></span> Document compliance monitoring</div><div><span><Check size={15}/></span> Deadline and workflow visibility</div></div></div><div className="login-left-footer"><span>AICTEFlow · Approval & Compliance</span><span>DEMO ENVIRONMENT</span></div><div className="login-decoration decoration-one"/><div className="login-decoration decoration-two"/></div><div className="login-right"><div className="login-form-wrap"><div className="mobile-login-brand"><Brand/></div><div className="login-heading"><span className="login-overline">WELCOME TO AICTEFLOW</span><h2>{mode==='register'?'Create your institution access':'Sign in to your workspace'}</h2><p>Choose your role to continue to the right portal.</p></div><div className="role-picker"><button className={role==='institution'?'role-option selected':''} onClick={()=>{setRole('institution');setError('');}} type="button"><span className="role-icon"><GraduationCap size={20}/></span><span><strong>Institution</strong><small>Submit & track applications</small></span>{role==='institution'&&<CheckCircle2 size={17} className="role-check"/>}</button><button className={role==='officer'?'role-option selected':''} onClick={()=>{setRole('officer');setError('');}} type="button"><span className="role-icon"><ShieldCheck size={20}/></span><span><strong>AICTE Officer</strong><small>Review & manage approvals</small></span>{role==='officer'&&<CheckCircle2 size={17} className="role-check"/>}</button><button className={role==='committee'?'role-option selected':''} onClick={()=>{setRole('committee');setError('');setMode('login');}} type="button"><span className="role-icon"><Users size={20}/></span><span><strong>EVC Committee</strong><small>Schedule & complete visits</small></span>{role==='committee'&&<CheckCircle2 size={17} className="role-check"/>}</button><button className={role==='authority'?'role-option selected':''} onClick={()=>{setRole('authority');setError('');setMode('login');}} type="button"><span className="role-icon"><ShieldCheck size={20}/></span><span><strong>Authority</strong><small>Reports & final decisions</small></span>{role==='authority'&&<CheckCircle2 size={17} className="role-check"/>}</button></div><form className="login-form" onSubmit={submit}>{mode==='register'&&<div className="form-field"><label>Institution name</label><input value={institutionName} onChange={e=>setInstitutionName(e.target.value)} required placeholder="Enter institution name"/></div>}<div className="form-field"><label>Email address</label><input type="email" autoComplete="username" placeholder={role==='officer'?'officer@aicte.gov.in':role==='committee'?'committee@aicte.gov.in':role==='authority'?'authority@aicte.gov.in':'office@institution.edu.in'} value={email} onChange={e=>setEmail(e.target.value)} required/></div><div className="form-field"><div className="label-row"><label>Password</label><span className="demo-note">Secure server sign-in</span></div><input type="password" autoComplete={mode==='register'?'new-password':'current-password'} placeholder="Enter any demo password" value={password} onChange={e=>setPassword(e.target.value)} required/></div>{error&&<div className="form-error"><AlertTriangle size={15}/>{error}</div>}<button className="btn btn-primary login-submit" type="submit">{mode==='register'?'Create demo access':'Sign in'} <ArrowRight size={17}/></button></form><div className="demo-hint"><ShieldCheck size={17}/><div><strong>Server-authenticated access</strong><p>Credentials are checked by Flask. Institution accounts can register here; officer accounts must be created by the local account setup script.</p></div></div>{role==='institution'&&<div className="register-link">New to the portal? <button onClick={()=>setMode(mode==='register'?'login':'register')}>{mode==='register'?'Back to sign in':'Create institution access'}</button></div>}<div className="login-legal">By continuing, you agree to use this demonstration system responsibly.</div></div></div></div>}

