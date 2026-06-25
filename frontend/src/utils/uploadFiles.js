export function selectedRawUploadFile(uploadFile) {
  if (!uploadFile) {
    return null;
  }
  if (uploadFile.raw) {
    return uploadFile.raw;
  }
  const fileConstructor = typeof File === 'undefined' ? null : File;
  if (fileConstructor && uploadFile instanceof fileConstructor) {
    return uploadFile;
  }
  return null;
}
